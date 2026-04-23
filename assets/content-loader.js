/**
 * CHF Content Loader
 * Dynamically loads page content from JSON data files.
 * Falls back gracefully to the hardcoded HTML if JSON is unavailable.
 */
(function() {
    'use strict';
    const VIDEO_EXT_REGEX = /\.(mp4|webm|mov|ogg)(\?|#|$)/i;
    const COLLECTION_VERSION_POLL_MS_ACTIVE = 1200;
    const COLLECTION_VERSION_POLL_MS_BACKGROUND = 5000;
    let isCollectionSyncInFlight = false;
    let lastCollectionSignature = '';
    let lastSeenSyncVersion = 0;
    let collectionSyncTimer = null;
    let activeCollectionRequest = null;
    let collectionRequestSeq = 0;

    // Determine current collection slug robustly across:
    // /slug, /slug/, /slug.html, /slug/index.html
    function resolveCollectionSlug() {
        const rawPath = window.location.pathname || '/';
        const normalized = rawPath.replace(/\/+$/, '');
        const segments = normalized.split('/').filter(Boolean);
        if (segments.length === 0) return '';

        let candidate = segments[segments.length - 1].replace(/\.html$/i, '');
        if (candidate.toLowerCase() === 'index' && segments.length > 1) {
            candidate = segments[segments.length - 2].replace(/\.html$/i, '');
        }
        return candidate;
    }
    const filename = resolveCollectionSlug();
    
    const VALID_PAGES = [
        'full-grown-avenue-trees',
        'exotic-indoor-plants',
        'bonsai',
        'curated-plants',
        'curated-specimens',
        'deep-solitude'
    ];

    if (!VALID_PAGES.includes(filename)) return;

    function getCollectionCacheKey(slug) {
        return `chf_collection_cache_v1_${slug}`;
    }

    function readCachedCollection(slug) {
        try {
            const raw = sessionStorage.getItem(getCollectionCacheKey(slug));
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== 'object' || !parsed.data) return null;
            return parsed.data;
        } catch (_) {
            return null;
        }
    }

    function writeCachedCollection(slug, data) {
        try {
            sessionStorage.setItem(getCollectionCacheKey(slug), JSON.stringify({
                savedAt: Date.now(),
                data
            }));
        } catch (_) {
            // Ignore storage quota/private mode failures.
        }
    }

    function syncCollectionContent() {
        if (isCollectionSyncInFlight) return;
        isCollectionSyncInFlight = true;
        const requestId = ++collectionRequestSeq;
        if (activeCollectionRequest) activeCollectionRequest.abort();
        activeCollectionRequest = new AbortController();

        fetch(`/api/data?slug=${filename}&t=${Date.now()}`, {
            cache: 'no-store',
            signal: activeCollectionRequest.signal
        })
            .then(res => {
                if (!res.ok) throw new Error('Not found');
                return res.json();
            })
            .then(data => {
                // Ignore stale responses if a newer sync started.
                if (requestId !== collectionRequestSeq) return;
                writeCachedCollection(filename, data);
                const signature = JSON.stringify(data);
                if (signature === lastCollectionSignature) return;
                safeRenderCollection(data);
                lastCollectionSignature = signature;
                console.log('[CHF] Collection live sync applied');
            })
            .catch((err) => {
                if (err && err.name === 'AbortError') return;
                // Keep current render when API is temporarily unavailable.
                console.log('[CHF] Collection sync unavailable');
            })
            .finally(() => {
                isCollectionSyncInFlight = false;
            });
    }

    async function checkCollectionSyncVersion(forceRefresh = false) {
        try {
            const res = await fetch(`/api/sync-version?t=${Date.now()}`, { cache: 'no-store' });
            if (!res.ok) return;
            const payload = await res.json();
            const incomingVersion = Number(payload?.version || 0);
            if (forceRefresh || !lastSeenSyncVersion || incomingVersion > lastSeenSyncVersion) {
                lastSeenSyncVersion = incomingVersion;
                syncCollectionContent();
            }
        } catch (_) {
            // Ignore transient polling failures.
        }
    }

    function safeRenderCollection(data) {
        try {
            const page = data && typeof data === 'object' ? (data.page || {}) : {};
            const categories = Array.isArray(data?.categories) ? data.categories : [];
            renderHero(page);
            renderCategories(categories);
        } catch (err) {
            // Keep existing DOM untouched if render fails, so refresh never "breaks" layout.
            console.error('[CHF] Render guard: keeping current layout due to render error', err);
        }
    }

    function scheduleCollectionSync() {
        if (collectionSyncTimer) clearTimeout(collectionSyncTimer);
        const interval = document.visibilityState === 'visible'
            ? COLLECTION_VERSION_POLL_MS_ACTIVE
            : COLLECTION_VERSION_POLL_MS_BACKGROUND;
        collectionSyncTimer = setTimeout(() => {
            checkCollectionSyncVersion(false);
            scheduleCollectionSync();
        }, interval);
    }

    // Initial sync + near-instant active-tab sync
    const cachedCollection = readCachedCollection(filename);
    if (cachedCollection) {
        safeRenderCollection(cachedCollection);
        lastCollectionSignature = JSON.stringify(cachedCollection);
    }
    syncCollectionContent();
    scheduleCollectionSync();
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            checkCollectionSyncVersion(true);
        }
        scheduleCollectionSync();
    });
    window.addEventListener('focus', () => checkCollectionSyncVersion(true));

    // Instant sync signal from admin publish (same browser/session).
    window.addEventListener('storage', (event) => {
        if (event.key === 'chf_content_sync') {
            checkCollectionSyncVersion(true);
        }
    });
    if ('BroadcastChannel' in window) {
        const syncChannel = new BroadcastChannel('chf-content-sync');
        syncChannel.addEventListener('message', () => checkCollectionSyncVersion(true));
    }

    function renderHero(page) {
        // Update hero section in a template-agnostic way across collection pages.
        const heroSection = document.querySelector('main > section.max-w-7xl');
        if (!heroSection) return;

        // Update breadcrumb if it exists
        const breadcrumb = heroSection.querySelector('.flex.items-center.gap-4 span.text-accent-bronze');
        if (breadcrumb) breadcrumb.textContent = page.breadcrumb || '';

        // Update title
        const h2 = heroSection.querySelector('h2');
        if (h2) {
            h2.innerHTML = `
                ${escHtml(page.titleLine1 || '')} <br />
                <span class="text-accent-bronze italic font-light drop-shadow-sm">${escHtml(page.titleLine2 || '')}</span>
            `;
        }

        // Update subtitle
        const subtitle = heroSection.querySelector('.text-gray-400');
        if (subtitle) subtitle.textContent = page.subtitle || '';
    }

    function renderCategories(categories) {
        const container = document.querySelector('.flex.flex-col.gap-32');
        if (!container) return;
        const existingBlocks = Array.from(container.children).filter((child) =>
            child.matches('.grid, .flex')
        );

        if (existingBlocks.length >= 4) {
            hydrateExistingBlocks(existingBlocks, categories);
            return;
        }

        // Use stable CSS class for injected layout consistency only as a fallback
        // when a page does not already ship with prebuilt block markup.
        container.classList.remove('gap-32');
        container.classList.add('feature-block-stack');

        if (!Array.isArray(categories) || categories.length === 0) {
            container.innerHTML = '';
            return;
        }

        container.innerHTML = categories.map((cat, i) => {
            const safeCat = cat && typeof cat === 'object' ? cat : {};
            const isReversed = i % 2 === 1;
            const mediaUrl = safeCat.image || '';
            const isCloudflareVideo = isCloudflareVideoUrl(mediaUrl);
            const isVideoFile = isVideoFileUrl(mediaUrl);
            const isVideo = isCloudflareVideo || isVideoFile;
            
            // Parse bullet points
            const bulletHtml = safeCat.features ? String(safeCat.features).split('\n').filter(f => f.trim()).map(f => `
                <li class="flex items-start gap-3 text-ivory/60">
                    <span class="w-1.5 h-px bg-accent-bronze mt-2.5 flex-shrink-0"></span>
                    <span class="text-sm font-light tracking-wide">${escHtml(f.trim())}</span>
                </li>
            `).join('') : '';

            return `
                <!-- ${safeCat.label || ''} -->
                <div class="feature-block-row ${isReversed ? 'is-reversed' : ''} group">
                    <!-- Media Column -->
                    <div class="feature-block-media-wrap reveal reveal-up stagger-1">
                        <div class="feature-block-media">
                            ${mediaUrl.length > 0 
                                ? (isVideo 
                                    ? (isCloudflareVideo
                                        ? `<iframe src="${getCloudflareEmbedUrl(mediaUrl)}" class="w-full h-full object-cover transition-transform duration-[3s] group-hover:scale-105" frameborder="0" allow="accelerometer; gyroscope; autoplay; encrypted-media; picture-in-picture;" allowfullscreen></iframe>`
                                        : `<video src="${getPlayableVideoUrl(mediaUrl)}" class="w-full h-full object-cover transition-transform duration-[3s] group-hover:scale-105" autoplay muted loop playsinline></video>`)
                                : `<img src="${mediaUrl}" alt="${escHtml(safeCat.title || '')}" class="w-full h-full object-cover transition-transform duration-[2.2s] group-hover:scale-105" loading="lazy" decoding="async" />`)
                                : ``
                            }
                            <!-- Decorative overlay -->
                            <div class="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent pointer-events-none"></div>
                        </div>
                    </div>

                    <!-- Text Column -->
                    <div class="feature-block-content ${isReversed ? 'text-right lg:text-left' : ''} reveal reveal-up stagger-2">
                        <div class="space-y-3">
                            <span class="feature-block-label">${escHtml(safeCat.label || '')}</span>
                            <h3 class="font-serif text-2xl md:text-4xl text-ivory leading-tight">
                                ${escHtml(safeCat.title || '')}
                            </h3>
                        </div>

                        <div class="space-y-3">
                            <p class="feature-block-copy mb-0">
                                ${escHtml(safeCat.description || '')}
                            </p>

                            <!-- Features / Bullet Points -->
                            ${bulletHtml ? `
                                <ul class="space-y-2 pt-1">
                                    ${bulletHtml}
                                </ul>
                            ` : ''}
                        </div>

                        <div class="pt-3">
                            <a href="${escHtml(safeCat.ctaLink || '#')}" 
                                class="feature-block-cta hover:text-accent-bronze transition-all group/btn">
                                <span>${escHtml(safeCat.ctaText || '')}</span>
                                <span class="w-6 h-px bg-accent-bronze group-hover/btn:w-10 transition-all"></span>
                            </a>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        // Trigger animation refresh if needed
        if (window.gsap && window.ScrollTrigger) {
            ScrollTrigger.refresh();
        }
    }

    function hydrateExistingBlocks(blocks, categories) {
        const safeCategories = Array.isArray(categories) ? categories.slice(0, blocks.length) : [];
        blocks.forEach((block, index) => {
            const safeCat = safeCategories[index] && typeof safeCategories[index] === 'object'
                ? safeCategories[index]
                : {};
            const mediaUrl = safeCat.image || '';
            const mediaFrame = block.querySelector('.relative.overflow-hidden');
            const labelEl = block.querySelector('span');
            const titleEl = block.querySelector('h3');
            const copyEl = block.querySelector('p');
            const ctaEl = block.querySelector('a[href]');

            if (labelEl) labelEl.textContent = safeCat.label || '';
            if (titleEl) titleEl.textContent = safeCat.title || '';
            if (copyEl) copyEl.textContent = safeCat.description || '';
            if (ctaEl) {
                ctaEl.textContent = safeCat.ctaText || '';
                ctaEl.setAttribute('href', safeCat.ctaLink || '#');
            }

            if (!mediaFrame) return;
            hydrateBlockMedia(mediaFrame, mediaUrl, safeCat.title || '', index);
        });
    }

    function hydrateBlockMedia(mediaFrame, mediaUrl, altText, index) {
        const desiredType = resolveMediaType(mediaUrl);
        const currentType = mediaFrame.getAttribute('data-media-type') || '';
        const currentSrc = mediaFrame.getAttribute('data-media-src') || '';
        if (desiredType === currentType && mediaUrl === currentSrc) return;

        mediaFrame.setAttribute('data-media-type', desiredType);
        mediaFrame.setAttribute('data-media-src', mediaUrl || '');
        mediaFrame.innerHTML = buildStaticBlockMedia(mediaUrl, altText);

        // Prioritize above-the-fold blocks; lazy-load deeper blocks.
        const mediaEl = mediaFrame.querySelector('img,video,iframe');
        if (!mediaEl) return;
        if (mediaEl.tagName === 'IMG') {
            mediaEl.loading = index <= 1 ? 'eager' : 'lazy';
            mediaEl.decoding = 'async';
        } else if (mediaEl.tagName === 'VIDEO') {
            mediaEl.preload = index === 0 ? 'metadata' : 'none';
        } else if (mediaEl.tagName === 'IFRAME') {
            mediaEl.loading = index === 0 ? 'eager' : 'lazy';
        }
    }

    function resolveMediaType(mediaUrl) {
        if (!mediaUrl) return 'placeholder';
        if (isCloudflareVideoUrl(mediaUrl)) return 'iframe-video';
        if (isVideoFileUrl(mediaUrl)) return 'file-video';
        return 'image';
    }

    function buildStaticBlockMedia(mediaUrl, altText) {
        if (!mediaUrl) {
            return '';
        }

        if (isCloudflareVideoUrl(mediaUrl)) {
            return `<iframe src="${getCloudflareEmbedUrl(mediaUrl)}" class="absolute inset-0 w-full h-full object-cover transition-transform duration-[2s] hover:scale-105" frameborder="0" allow="accelerometer; gyroscope; autoplay; encrypted-media; picture-in-picture;" allowfullscreen></iframe>`;
        }

        if (isVideoFileUrl(mediaUrl)) {
            return `<video src="${getPlayableVideoUrl(mediaUrl)}" class="absolute inset-0 w-full h-full object-cover transition-transform duration-[2s] hover:scale-105" autoplay muted loop playsinline></video>`;
        }

        return `<img src="${escHtml(mediaUrl)}" alt="${escHtml(altText)}" class="absolute inset-0 w-full h-full object-cover transition-transform duration-[2s] hover:scale-105" loading="lazy" decoding="async" />`;
    }

    function escHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function isCloudflareVideoUrl(url) {
        if (!url) return false;
        try {
            const parsed = new URL(url, window.location.origin);
            const host = parsed.hostname.toLowerCase();
            return host.includes('videodelivery.net') || host.includes('cloudflarestream.com');
        } catch (_) {
            return false;
        }
    }

    function isVideoFileUrl(url) {
        if (!url) return false;
        return VIDEO_EXT_REGEX.test(String(url));
    }

    function getCloudflareEmbedUrl(url) {
        try {
            const parsed = new URL(url, window.location.origin);
            let videoId = '';

            if (parsed.hostname.toLowerCase().includes('iframe.videodelivery.net')) {
                videoId = parsed.pathname.split('/').filter(Boolean)[0] || '';
            } else if (parsed.hostname.toLowerCase().includes('videodelivery.net')) {
                videoId = parsed.pathname.split('/').filter(Boolean)[0] || '';
            } else if (parsed.hostname.toLowerCase().includes('cloudflarestream.com')) {
                videoId = parsed.pathname.split('/').filter(Boolean).pop() || '';
            }

            if (!videoId) return url;
            return `https://iframe.videodelivery.net/${videoId}?autoplay=true&muted=true&loop=true&preload=true`;
        } catch (_) {
            return url;
        }
    }

    function getPlayableVideoUrl(url) {
        if (!url) return url;
        try {
            const parsed = new URL(url, window.location.origin);
            if (parsed.hostname.toLowerCase().endsWith('.r2.dev')) {
                return `/api/r2-media?url=${encodeURIComponent(parsed.href)}`;
            }
            return parsed.href;
        } catch (_) {
            return url;
        }
    }
})();
