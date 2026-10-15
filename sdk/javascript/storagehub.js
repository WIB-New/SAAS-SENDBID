/**
 * StorageHub JavaScript SDK
 * Compatible navigateur (fetch API) et Node.js (18+)
 *
 * Usage :
 *   import { StorageHub } from './storagehub.js';
 *
 *   const hub = new StorageHub({
 *     apiKey: 'sk-...',
 *     baseUrl: 'https://storage.sendbid.com',
 *     userId: 'user-001',
 *     role: 'user',
 *   });
 *
 *   // Upload d'un fichier depuis un <input type="file">
 *   const result = await hub.upload(fileInput.files[0], 'avatars');
 *   console.log(result.url);
 *
 *   // Lister les fichiers avec pagination
 *   const { items, total, pages } = await hub.listFiles({ category: 'avatars', page: 1 });
 *
 *   // URL signée (accès temporaire)
 *   const { signed_url } = await hub.getSignedUrl(result.file_id, { ttl: 60 });
 *
 *   // Supprimer
 *   await hub.delete(result.file_id);
 */

export class StorageHubError extends Error {
  constructor(statusCode, code, message) {
    super(`[${statusCode}] ${code}: ${message}`);
    this.statusCode = statusCode;
    this.code = code;
    this.apiMessage = message;
  }
}

export class StorageHub {
  /**
   * @param {object} config
   * @param {string} config.apiKey      - Clé API StorageHub
   * @param {string} [config.baseUrl]   - URL de base du service (défaut: origine courante)
   * @param {string} [config.userId]    - Identifiant utilisateur final
   * @param {string} [config.role]      - Rôle utilisateur ('user' | 'admin')
   * @param {number} [config.timeout]   - Timeout en ms (défaut: 30000)
   */
  constructor({ apiKey, baseUrl, userId = 'sdk-user', role = 'user', timeout = 30000 } = {}) {
    this.apiKey  = apiKey;
    this.baseUrl = (baseUrl || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8080')).replace(/\/$/, '');
    this.userId  = userId;
    this.role    = role;
    this.timeout = timeout;
  }

  get _headers() {
    return {
      'X-API-Key':   this.apiKey,
      'X-User-Id':   this.userId,
      'X-User-Role': this.role,
    };
  }

  async _request(method, path, { body, params, isFormData = false } = {}) {
    let url = `${this.baseUrl}${path}`;
    if (params) {
      const qs = new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v != null))
      );
      if ([...qs].length) url += '?' + qs.toString();
    }

    const headers = { ...this._headers };
    let fetchBody;

    if (body instanceof FormData || isFormData) {
      fetchBody = body;
      // Ne pas setter Content-Type — fetch le fait automatiquement avec boundary
    } else if (body) {
      headers['Content-Type'] = 'application/json';
      fetchBody = JSON.stringify(body);
    }

    const controller = new AbortController();
    const timerId = setTimeout(() => controller.abort(), this.timeout);

    let resp;
    try {
      resp = await fetch(url, { method, headers, body: fetchBody, signal: controller.signal });
    } finally {
      clearTimeout(timerId);
    }

    let data;
    const ct = resp.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      data = await resp.json();
    } else {
      data = { raw: await resp.text() };
    }

    if (!resp.ok || data?.success === false) {
      throw new StorageHubError(resp.status, data?.code || 'UNKNOWN', data?.error || 'Unknown error');
    }

    return data;
  }

  // ── Upload ──────────────────────────────────────────────────────────────────

  /**
   * Upload un fichier File/Blob.
   * @param {File|Blob} file
   * @param {'avatars'|'kyc'|'receipts'} category
   * @param {object} [options]
   * @param {object} [options.tags]           - Tags JSON
   * @param {string} [options.replacesFileId] - ID du fichier à remplacer
   */
  async upload(file, category, { tags, replacesFileId } = {}) {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('category', category);
    if (tags)           fd.append('tags', JSON.stringify(tags));
    if (replacesFileId) fd.append('replaces_file_id', replacesFileId);
    return this._request('POST', '/v1/files', { body: fd });
  }

  /**
   * Upload depuis une URL distante.
   * @param {string} remoteUrl
   * @param {'avatars'|'kyc'|'receipts'} category
   * @param {object} [tags]
   */
  async uploadFromUrl(remoteUrl, category, tags = null) {
    return this._request('POST', '/v1/files/from-url', {
      body: { url: remoteUrl, category, tags },
    });
  }

  /**
   * Upload plusieurs fichiers en une seule requête.
   * @param {File[]} files
   * @param {'avatars'|'kyc'|'receipts'} category
   */
  async uploadBulk(files, category) {
    const fd = new FormData();
    for (const f of files) fd.append('files', f);
    fd.append('category', category);
    return this._request('POST', '/v1/files/bulk', { body: fd });
  }

  // ── Lecture ─────────────────────────────────────────────────────────────────

  /**
   * Liste les fichiers avec pagination.
   * @param {object} [options]
   * @param {string} [options.category]
   * @param {number} [options.page]
   * @param {number} [options.limit]
   * @param {string} [options.sort]  - ex: 'created_at:desc'
   * @returns {{ items, total, page, limit, pages }}
   */
  async listFiles({ category, page = 1, limit = 20, sort = 'created_at:desc' } = {}) {
    return this._request('GET', '/v1/files', { params: { category, page, limit, sort } });
  }

  /** Métadonnées d'un fichier. */
  async getMeta(fileId) {
    return this._request('GET', `/v1/files/${fileId}/meta`);
  }

  /** Historique des versions. */
  async getVersions(fileId) {
    return this._request('GET', `/v1/files/${fileId}/versions`);
  }

  /**
   * Génère une URL signée temporaire.
   * @param {string} fileId
   * @param {object} [options]
   * @param {number} [options.ttl] - Durée en secondes (défaut: 60)
   */
  async getSignedUrl(fileId, { ttl } = {}) {
    return this._request('GET', `/v1/files/${fileId}/signed`, { params: { ttl } });
  }

  /**
   * Télécharge le contenu d'un fichier (retourne un Blob).
   * @param {string} fileId
   */
  async download(fileId) {
    const resp = await fetch(`${this.baseUrl}/v1/files/${fileId}`, { headers: this._headers });
    if (!resp.ok) throw new StorageHubError(resp.status, 'DOWNLOAD_ERROR', 'Download failed');
    return resp.blob();
  }

  // ── Modification ────────────────────────────────────────────────────────────

  /**
   * Met à jour les tags d'un fichier.
   * @param {string} fileId
   * @param {object} tags
   */
  async updateTags(fileId, tags) {
    return this._request('PATCH', `/v1/files/${fileId}/tags`, { body: { tags } });
  }

  /**
   * Remplace un fichier par une nouvelle version.
   * @param {string} fileId
   * @param {File|Blob} newFile
   */
  async replace(fileId, newFile) {
    const fd = new FormData();
    fd.append('file', newFile);
    return this._request('POST', `/v1/files/${fileId}/replace`, { body: fd });
  }

  /** Supprime (soft delete) un fichier. */
  async delete(fileId) {
    return this._request('DELETE', `/v1/files/${fileId}`);
  }

  // ── Webhooks ────────────────────────────────────────────────────────────────

  /**
   * Enregistre un endpoint webhook.
   * @param {string} url         - URL HTTPS du endpoint
   * @param {string} [events]    - '*' ou 'file.uploaded,file.deleted'
   * @param {string} [secret]    - Secret HMAC pour vérifier les payloads
   */
  async createWebhook(url, events = '*', secret = null) {
    return this._request('POST', '/v1/webhooks', { body: { url, events, secret } });
  }

  /** Liste les webhooks enregistrés. */
  async listWebhooks() {
    return this._request('GET', '/v1/webhooks');
  }

  /** Supprime un webhook. */
  async deleteWebhook(webhookId) {
    return this._request('DELETE', `/v1/webhooks/${webhookId}`);
  }

  /** Historique des livraisons d'un webhook. */
  async webhookDeliveries(webhookId) {
    return this._request('GET', `/v1/webhooks/${webhookId}/deliveries`);
  }

  // ── Compte & stats ──────────────────────────────────────────────────────────

  /** Statistiques d'usage du compte. */
  async getStats() {
    return this._request('GET', '/v1/accounts/stats');
  }

  /** État de santé du service. */
  async health() {
    return this._request('GET', '/health');
  }

  /** Liveness probe. */
  async ping() {
    const data = await this._request('GET', '/v1/ping');
    return data?.pong === true;
  }
}

// ── Export CommonJS pour Node.js sans ESM ──────────────────────────────────────
if (typeof module !== 'undefined') {
  module.exports = { StorageHub, StorageHubError };
}
