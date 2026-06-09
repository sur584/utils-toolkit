/**
 * Parametrized global store factory.
 * Each tool creates its own store instance via createStore().
 * Provides image management, selection tracking, and reactive subscriptions.
 */

import { useState, useEffect } from 'react';
import { uid, isImgFile } from './utils.js';

/**
 * Create a new isolated store instance.
 * @returns {Object} Store with images, selection, and subscription methods.
 */
export function createStore() {
  let _images = [];
  let _sel = new Set();
  let _listeners = [];

  function notify() {
    _listeners.forEach((fn) => fn());
  }

  return {
    /** @returns {Array} Current image list */
    get images() {
      return _images;
    },

    /** @param {Array} v - Replace entire image list and notify */
    set images(v) {
      _images = v;
      notify();
    },

    /** @returns {Set} Current selection set of image IDs */
    get sel() {
      return _sel;
    },

    /**
     * Add files to the image list. Filters for supported image types,
     * creates thumbnail URLs, and triggers dimension loading.
     * @param {File[]} files
     * @param {Object} [opts] - Additional fields to attach to each image item
     * @returns {Object[]} The newly created image items
     */
    addImages(files, opts = {}) {
      const valid = Array.from(files).filter(isImgFile);
      if (!valid.length) return [];

      const newItems = valid.map((f) => ({
        id: uid(),
        file: f,
        name: f.name,
        size: f.size,
        type: f.type,
        thumb: URL.createObjectURL(f),
        status: 'idle',
        w: 0,
        h: 0,
        ...opts,
      }));

      // Load dimensions asynchronously
      newItems.forEach((item) => {
        const t = new Image();
        t.onload = () => {
          item.w = t.naturalWidth;
          item.h = t.naturalHeight;
          notify();
        };
        t.src = URL.createObjectURL(item.file);
      });

      _images = [..._images, ...newItems];
      notify();
      return newItems;
    },

    /**
     * Remove a single image by ID and revoke its URLs.
     * @param {string} id
     */
    rmImg(id) {
      const img = _images.find((x) => x.id === id);
      if (img) {
        URL.revokeObjectURL(img.thumb);
        if (img.cUrl) URL.revokeObjectURL(img.cUrl);
        if (img.resultUrl) URL.revokeObjectURL(img.resultUrl);
      }
      _images = _images.filter((x) => x.id !== id);
      _sel.delete(id);
      notify();
    },

    /** Remove all images and revoke all URLs. */
    clearAll() {
      _images.forEach((img) => {
        URL.revokeObjectURL(img.thumb);
        if (img.cUrl) URL.revokeObjectURL(img.cUrl);
        if (img.resultUrl) URL.revokeObjectURL(img.resultUrl);
      });
      _images = [];
      _sel.clear();
      notify();
    },

    /**
     * Update properties on a single image by ID.
     * @param {string} id
     * @param {Object} updates - Properties to merge
     */
    upd(id, updates) {
      _images = _images.map((i) => (i.id === id ? { ...i, ...updates } : i));
      notify();
    },

    /**
     * Toggle an image in/out of the selection set.
     * @param {string} id
     */
    toggleSel(id) {
      if (_sel.has(id)) _sel.delete(id);
      else _sel.add(id);
      notify();
    },

    /** Select all images. */
    selectAll() {
      _images.forEach((i) => _sel.add(i.id));
      notify();
    },

    /** Deselect all images. */
    deselectAll() {
      _sel.clear();
      notify();
    },

    /**
     * Subscribe to state changes. Returns an unsubscribe function.
     * @param {Function} fn - Callback invoked on each change
     * @returns {Function} Unsubscribe function
     */
    sub(fn) {
      _listeners.push(fn);
      return () => {
        _listeners = _listeners.filter((l) => l !== fn);
      };
    },

    /** Manually trigger notification to all subscribers. */
    notify() {
      notify();
    },
  };
}

/**
 * React hook that subscribes a component to a store instance.
 * The component re-renders on every store notification.
 * @param {Object} store - Store created by createStore()
 * @returns {Object} { images, sel, ...storeMethods }
 */
export function useStore(store) {
  const [, forceUpdate] = useState(0);
  useEffect(() => {
    const unsub = store.sub(() => forceUpdate((x) => x + 1));
    return unsub;
  }, [store]);
  return {
    images: store.images,
    sel: store.sel,
    addImages: store.addImages.bind(store),
    rmImg: store.rmImg.bind(store),
    clearAll: store.clearAll.bind(store),
    upd: store.upd.bind(store),
    toggleSel: store.toggleSel.bind(store),
    selectAll: store.selectAll.bind(store),
    deselectAll: store.deselectAll.bind(store),
    notify: store.notify.bind(store),
  };
}
