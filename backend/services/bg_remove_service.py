"""
背景移除服务 - 封装完整的抠图处理流水线
从 main.py 中提取，统一单张、批量、SSE 三种调用方式的共享逻辑。

流水线步骤:
1. 预处理图片（解码 + 颜色模式归一化 + 尺寸限制）
2. 图片分类（ImageClassifier）
3. 模型路由（ModelRouter）
4. 二次尺寸适配（如果路由后的模型有更严格限制）
5. rembg 推理
6. 后处理边缘优化（PostProcessor）
7. 编码输出
"""

import io
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class BgRemoveService:
    """背景移除服务 - 依赖注入模式，接收所有子服务实例"""

    def __init__(
        self,
        model_manager,
        image_classifier,
        model_router,
        image_optimizer,
        post_processor,
        disk_cache,
    ):
        self.model_manager = model_manager
        self.image_classifier = image_classifier
        self.model_router = model_router
        self.image_optimizer = image_optimizer
        self.post_processor = post_processor
        self.disk_cache = disk_cache

    def process_image(
        self,
        image_bytes: bytes,
        model: str = None,
        output_format: str = "png",
        batch_size: int = 1,
    ) -> tuple:
        """
        处理单张图片的完整抠图流水线。

        Args:
            image_bytes: 原始图片字节
            model: 用户指定的模型名（None 或 'auto' 时自动路由）
            output_format: 输出格式 ('png' 或 'webp')
            batch_size: 批量大小（影响模型路由降级策略）

        Returns:
            (result_bytes, metadata_dict)
            metadata 包含: classification, model_used, cache_hit, processing_time

        Raises:
            ValueError: 图片格式错误、损坏或尺寸太小
        """
        from rembg import remove

        # 1. 预处理（解码 + 颜色模式 + 默认模型尺寸限制）
        processed = self.image_optimizer.preprocess(image_bytes, "bria-rmbg")

        # 2. 图片分类
        classification = self.image_classifier.classify(processed)

        # 3. 模型路由
        selected_model = self.model_router.select_model(
            classification=classification,
            batch_size=batch_size,
            explicit_model=model,
        )

        # 4. 如果路由后的模型有更严格的尺寸限制，重新预处理
        max_dim = self.image_optimizer.get_max_dim(selected_model)
        if max(processed.size) > max_dim:
            processed = self.image_optimizer.preprocess(image_bytes, selected_model)

        # 5. 推理
        session = self.model_manager.get_session(selected_model)
        kwargs = dict(session=session)

        alpha_params = self.post_processor.get_alpha_params(selected_model)
        if alpha_params.get("enabled"):
            kwargs["alpha_matting"] = True
            kwargs["alpha_matting_foreground_threshold"] = alpha_params[
                "foreground_threshold"
            ]
            kwargs["alpha_matting_background_threshold"] = alpha_params[
                "background_threshold"
            ]
            kwargs["alpha_matting_erode_size"] = alpha_params["erode_size"]

        result = remove(processed, **kwargs)

        # 6. 后处理（边缘优化）+ 7. 编码输出
        if hasattr(result, "save"):
            result = self.post_processor.process(result, selected_model)
            buf = io.BytesIO()
            save_format = "WEBP" if output_format == "webp" else "PNG"
            result.save(
                buf,
                format=save_format,
                quality=90 if output_format == "webp" else None,
            )
            output_data = buf.getvalue()
        else:
            output_data = result

        return output_data, classification, selected_model

    def check_cache(self, image_bytes: bytes, model: str) -> Optional[bytes]:
        """
        检查缓存是否命中。

        Args:
            image_bytes: 原始图片字节
            model: 模型标识

        Returns:
            缓存的图片字节，未命中返回 None
        """
        cache_key = self.disk_cache.make_key(image_bytes, model)
        return self.disk_cache.get(cache_key)

    def put_cache(
        self,
        image_bytes: bytes,
        model: str,
        output_data: bytes,
        classification: str,
        selected_model: str,
    ):
        """
        将处理结果写入缓存。

        Args:
            image_bytes: 原始图片字节（用于生成 cache key）
            model: 用户请求时指定的模型标识
            output_data: 处理后的图片字节
            classification: 图片分类结果
            selected_model: 实际使用的模型名
        """
        cache_key = self.disk_cache.make_key(image_bytes, model)
        self.disk_cache.put(
            cache_key,
            output_data,
            {
                "classification": classification,
                "model": selected_model,
            },
        )

    def process_single(
        self,
        image_bytes: bytes,
        model: str = None,
        output_format: str = "png",
        batch_size: int = 1,
    ) -> tuple:
        """
        带缓存的单张图片处理（供外部直接调用）。

        Args:
            image_bytes: 原始图片字节
            model: 用户指定的模型名
            output_format: 输出格式
            batch_size: 批量大小

        Returns:
            (result_bytes, metadata_dict)
            metadata: classification, model_used, cache_hit(bool), processing_time_ms(int)
        """
        start = time.time()

        # 缓存检查
        cache_hit = False
        cached = self.check_cache(image_bytes, model or "auto")
        if cached:
            elapsed_ms = int((time.time() - start) * 1000)
            return cached, {
                "classification": None,
                "model_used": None,
                "cache_hit": True,
                "processing_time_ms": elapsed_ms,
            }

        # 处理
        output_data, classification, selected_model = self.process_image(
            image_bytes,
            model=model,
            output_format=output_format,
            batch_size=batch_size,
        )

        # 写入缓存
        self.put_cache(image_bytes, model or "auto", output_data, classification, selected_model)

        elapsed_ms = int((time.time() - start) * 1000)
        return output_data, {
            "classification": classification,
            "model_used": selected_model,
            "cache_hit": False,
            "processing_time_ms": elapsed_ms,
        }

    def process_batch(
        self,
        items: list,
        model: str = None,
        output_format: str = "png",
    ) -> list:
        """
        批量处理多张图片（不含缓存检查，供 batch 端点的 process_one 闭包使用）。

        与 process_image 相同的流水线，区别在于 batch_size 传入实际批量大小
        以触发模型降级策略。

        Args:
            items: [(index, filename, image_bytes), ...] 元组列表
            model: 用户指定的模型名
            output_format: 输出格式

        Returns:
            [(index, result_dict), ...] 与输入等长的结果列表
        """
        results = []
        batch_size = len(items)
        for idx, filename, image_bytes in items:
            try:
                output_data, classification, selected_model = self.process_image(
                    image_bytes,
                    model=model,
                    output_format=output_format,
                    batch_size=batch_size,
                )

                # 生成输出文件名
                base = filename.rsplit(".", 1)[0] if filename else "image"
                ext = "webp" if output_format == "webp" else "png"
                out_name = f"{base}_remove.{ext}"

                # 写入缓存
                self.put_cache(
                    image_bytes, selected_model, output_data, classification, selected_model
                )

                results.append(
                    (
                        idx,
                        {
                            "filename": out_name,
                            "original_filename": filename,
                            "success": True,
                            "classification": classification,
                            "model": selected_model,
                        },
                    )
                )
            except Exception as e:
                logger.error(f"批量抠图失败 {filename}: {e}", exc_info=True)
                results.append(
                    (
                        idx,
                        {
                            "filename": filename,
                            "success": False,
                            "error": str(e)[:200],
                        },
                    )
                )
        return results

    def process_stream_item(
        self,
        image_bytes: bytes,
        filename: str,
        model: str = None,
        batch_size: int = 1,
    ) -> dict:
        """
        处理单张图片用于 SSE 流式输出（无缓存写入）。

        Args:
            image_bytes: 原始图片字节
            filename: 原始文件名
            model: 用户指定的模型名
            batch_size: 批量大小

        Returns:
            {'success': True, 'filename': out_name} 或
            {'success': False, 'filename': filename, 'error': msg}
        """
        try:
            output_data, classification, selected_model = self.process_image(
                image_bytes,
                model=model,
                output_format="png",
                batch_size=batch_size,
            )

            base = filename.rsplit(".", 1)[0] if filename else "image"
            out_name = f"{base}_remove.png"

            return {
                "success": True,
                "filename": out_name,
                "output_data": output_data,
                "classification": classification,
                "model_used": selected_model,
            }
        except Exception as e:
            logger.error(f"SSE 抠图失败 {filename}: {e}", exc_info=True)
            return {
                "success": False,
                "filename": filename,
                "error": str(e)[:200],
            }
