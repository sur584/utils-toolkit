/**
 * Shared React hooks for utils-toolkit tools.
 */

import { useState, useRef, useCallback } from 'react';

/**
 * Zoom and pan hook for image preview panels.
 * Identical logic extracted from bg-remover and text-remover.
 *
 * @returns {{ zoom: number, setZoom: Function, pan: {x:number,y:number}, setPan: Function, handleWheel: Function, handlePanDown: Function, handlePanMove: Function, handlePanUp: Function, handleZoomReset: Function }}
 */
export function useZoomPan() {
  var zoomState = useState(1);
  var zoom = zoomState[0];
  var setZoom = zoomState[1];

  var panState = useState({ x: 0, y: 0 });
  var pan = panState[0];
  var setPan = panState[1];

  var panDragging = useRef(false);
  var panStart = useRef({ x: 0, y: 0 });

  var handleWheel = useCallback(function (e) {
    e.preventDefault();
    var delta = e.deltaY > 0 ? -0.15 : 0.15;
    setZoom(function (z) { return Math.max(0.25, Math.min(10, z + delta)); });
  }, []);

  var handlePanDown = useCallback(function (e) {
    if (zoom <= 1) return;
    panDragging.current = true;
    panStart.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
    e.currentTarget.style.cursor = 'grabbing';
  }, [zoom, pan]);

  var handlePanMove = useCallback(function (e) {
    if (!panDragging.current) return;
    setPan({ x: e.clientX - panStart.current.x, y: e.clientY - panStart.current.y });
  }, []);

  var handlePanUp = useCallback(function () {
    panDragging.current = false;
  }, []);

  var handleZoomReset = useCallback(function () {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  return {
    zoom: zoom,
    setZoom: setZoom,
    pan: pan,
    setPan: setPan,
    panDragging: panDragging,
    handleWheel: handleWheel,
    handlePanDown: handlePanDown,
    handlePanMove: handlePanMove,
    handlePanUp: handlePanUp,
    handleZoomReset: handleZoomReset,
  };
}
