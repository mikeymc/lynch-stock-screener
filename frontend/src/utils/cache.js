/**
 * Browser-side cache for screening results using IndexedDB.
 * Improves performance by avoiding re-fetching/re-scoring stocks on every page load.
 */

const DB_NAME = 'ScreeningCache';
const STORE_NAME = 'screening';
const DB_VERSION = 1;

class ScreeningCache {
    constructor() {
        this.db = null;
        this.initPromise = this.init();
    }

    init() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onerror = (event) => {
                console.error('ScreeningCache open error:', event.target.error);
                reject(event.target.error);
            };

            request.onsuccess = (event) => {
                this.db = event.target.result;
                resolve(this.db);
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    db.createObjectStore(STORE_NAME); // Key is the cache key string
                }
            };
        });
    }

    async getDb() {
        if (!this.db) {
            await this.initPromise;
        }
        return this.db;
    }

    /**
     * meaningfulKey: string constructed from params
     */
    _getKey(userId, characterId) {
        const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
        return `screening_${userId}_${characterId}_${today}`;
    }

    async getResults(userId, characterId) {
        try {
            const db = await this.getDb();
            const key = this._getKey(userId, characterId);

            return new Promise((resolve, reject) => {
                const transaction = db.transaction([STORE_NAME], 'readonly');
                const store = transaction.objectStore(STORE_NAME);
                const request = store.get(key);

                request.onsuccess = () => {
                    resolve(request.result); // Returns undefined if not found
                };
                request.onerror = () => {
                    console.warn('Cache get error', request.error);
                    resolve(null); // Fail gracefully
                };
            });
        } catch (err) {
            console.error('Cache get exception:', err);
            return null;
        }
    }

    async saveResults(userId, characterId, data) {
        try {
            const db = await this.getDb();
            const key = this._getKey(userId, characterId);

            return new Promise((resolve, reject) => {
                const transaction = db.transaction([STORE_NAME], 'readwrite');
                const store = transaction.objectStore(STORE_NAME);
                const request = store.put(data, key);

                request.onsuccess = () => resolve();
                request.onerror = () => reject(request.error);
            });
        } catch (err) {
            console.error('Cache save exception:', err);
        }
    }

    async clear() {
        try {
            const db = await this.getDb();
            return new Promise((resolve, reject) => {
                const transaction = db.transaction([STORE_NAME], 'readwrite');
                const store = transaction.objectStore(STORE_NAME);
                const request = store.clear();

                request.onsuccess = () => resolve();
                request.onerror = () => reject(request.error);
            });
        } catch (err) {
            console.error('Cache clear exception:', err);
        }
    }
}

export const screeningCache = new ScreeningCache();
