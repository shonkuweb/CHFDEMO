/**
 * CHF Universal CMS Core
 * Standardizes content loading across all site pages.
 * Supports progressive video loading: static image shows instantly,
 * video crossfades in smoothly once buffered enough to play.
 */
(function() {
    const DEBUG = true;
    const VIDEO_EXTS = ['.mp4', '.webm', '.mov', '.ogg'];
    const HERO_VIDEO_ASPECT = 1280 / 613; // width / height
    const CMS_VERSION_POLL_MS_ACTIVE = 1200;
    const CMS_VERSION_POLL_MS_BACKGROUND = 5000;
    let isSyncInFlight = false;
    let lastCmsSignature = '';
    let lastSeenSyncVersion = 0;
    let cmsSyncTimer = null;

    function isVideoUrl(url) {
        if (!url) return false;
        if (isCloudflareVideoUrl(url)) return true;
        const clean = String(url).split('?')[0].toLowerCase();
        return VIDEO_EXTS.some(ext => clean.endsWith(ext));
    }

    function isCloudflareVideoUrl(url) {
        try {
            const parsed = new URL(url, window.location.origin);
            const host = parsed.hostname.toLowerCase();
            return host.includes('videodelivery.net') || host.includes('cloudflarestream.com');
        } catch (_) {
            return false;
        }
    }

    function getPlayableVideoUrl(url) {
        try {
            const parsed = new URL(url, window.location.origin);
            // Prefer direct public URL delivery for fastest startup.
            // Backend proxying adds an extra network hop and slows first frame.
            return parsed.href;
        } catch (_) {
            return url;
        }
    }

    function getCloudflareEmbedUrl(url) {
        try {
            const parsed = new URL(url, window.location.origin);
            const host = parsed.hostname.toLowerCase();
            let videoId = '';

            if (host.includes('iframe.videodelivery.net') || host.includes('videodelivery.net')) {
                videoId = parsed.pathname.split('/').filter(Boolean)[0] || '';
            } else if (host.includes('cloudflarestream.com')) {
                videoId = parsed.pathname.split('/').filter(Boolean).pop() || '';
            }

            if (!videoId) return url;
            return `https://iframe.videodelivery.net/${videoId}?autoplay=true&muted=true&loop=true&preload=true`;
        } catch (_) {
            return url;
        }
    }

    function resolvePageSlug() {
        const rawPath = window.location.pathname || '/';
        const normalized = rawPath.replace(/\/+$/, '');
        const segments = normalized.split('/').filter(Boolean);
        
        if (segments.length === 0) return 'home';

        let candidate = segments[segments.length - 1].replace(/\.html$/i, '');
        if (candidate.toLowerCase() === 'index') {
            return segments.length > 1 
                ? segments[segments.length - 2].replace(/\.html$/i, '') 
                : 'home';
        }
        return candidate;
    }

    const PAGE_PREFIX_MAP = {
        'home': 'home',
        'index': 'home',
        'architectural-harmony': 'arch',
        'plant-experience-center': 'plant-center',
        'white-glove-service': 'whiteglove',
        'deep-solitude': 'deep',
        'curated-specimens': 'specimens',
        'bonsai': 'bonsai',
        'full-grown-avenue-trees': 'avenue',
        'exotic-indoor-plants': 'indoor',
        'curated-plants': 'curated',
        'about': 'about'
    };

    async function initCMS() {
        if (isSyncInFlight) return;
        isSyncInFlight = true;
        
        const slug = resolvePageSlug();
        const prefix = PAGE_PREFIX_MAP[slug] || slug;

        if (DEBUG) console.log(`[CMS] Initializing for slug: ${slug}, using prefix: ${prefix}`);

        try {
            const t = Date.now();
            const [pageRes, globalRes] = await Promise.all([
                fetch(`/api/site-content?page=${prefix}&t=${t}`, { cache: 'no-store' }),
                fetch(`/api/site-content?page=global&t=${t}`, { cache: 'no-store' })
            ]);

            const pageData = await pageRes.json();
            const globalData = await globalRes.json();
            // Merge: page content overrides global
            const cmsData = { ...globalData, ...pageData };
            const signature = JSON.stringify(cmsData);

            if (DEBUG) console.log(`[CMS] Content loaded for prefix "${prefix}":`, cmsData);
            if (signature !== lastCmsSignature) {
                applyContent(cmsData);
                lastCmsSignature = signature;
                if (DEBUG) console.log('[CMS] Live sync applied');
            }

        } catch (err) {
            console.error('[CMS] Failed to initialize:', err);
        } finally {
            isSyncInFlight = false;
        }
    }

    async function checkCmsSyncVersion(forceRefresh = false) {
        try {
            const res = await fetch(`/api/sync-version?t=${Date.now()}`, { cache: 'no-store' });
            if (!res.ok) return;
            const payload = await res.json();
            const incomingVersion = Number(payload?.version || 0);
            if (forceRefresh || !lastSeenSyncVersion || incomingVersion > lastSeenSyncVersion) {
                lastSeenSyncVersion = incomingVersion;
                await initCMS();
            }
        } catch (_) {
            // Ignore transient polling failures; next poll retries.
        }
    }

    function applyContent(data) {
        document.querySelectorAll('[data-cms]').forEach(el => {
            const path = el.getAttribute('data-cms');
            const content = data[path];

            if (!content) {
                if (DEBUG) console.warn(`[CMS] No data found for path: ${path}`);
                return;
            }

            const val  = content.value;
            const type = content.type;
            if (type === 'media') {
                if (el.tagName === 'IMG') {
                    el.src = val;
                } else if (el.tagName === 'VIDEO') {
                    el.src = val;
                } else {
                    // Container element (e.g. hero background div)
                    if (isVideoUrl(val)) {
                        if (isCloudflareVideoUrl(val)) {
                            applyHeroCloudflareEmbed(el, val);
                        } else {
                            applyHeroVideo(el, val);
                        }
                    } else {
                        // Image — remove any old injected video, apply as background
                        const oldVideo = el.querySelector('video.cms-hero-video');
                        if (oldVideo) oldVideo.remove();
                        const oldIframe = el.querySelector('iframe.cms-hero-video');
                        if (oldIframe) oldIframe.remove();
                        el.classList.add('bg-cover', 'bg-center', 'bg-no-repeat', 'bg-fixed');
                        el.style.backgroundImage = `url('${val}')`;
                    }
                }
            } else {
                // Text / longtext / HTML injection
                el.innerHTML = val;
            }
        });
    }

    /**
     * Progressive hero video loader.
     * Strategy:
     *   1. Keep the existing background-image visible immediately (zero blank time).
     *   2. Inject a hidden <video> element and begin buffering with preload="auto".
     *   3. On `canplay`, fade the video in over 800ms and then remove the bg-image.
     *   4. 8-second safety net forces the video visible even if canplay never fires.
     */
    function applyHeroVideo(el, videoUrl) {
        const oldIframe = el.querySelector('iframe.cms-hero-video');
        if (oldIframe) oldIframe.remove();

        // Ensure the element has a z-index context and overflow control
        el.style.position = 'relative';
        el.style.overflow = 'hidden';

        // Reuse or create the video element
        let videoEl = el.querySelector('video.cms-hero-video');
        if (!videoEl) {
            videoEl = document.createElement('video');
            videoEl.className   = 'cms-hero-video absolute inset-0 w-full h-full object-cover';
            videoEl.muted       = true;
            videoEl.loop        = true;
            videoEl.autoplay    = true;
            videoEl.playsInline = true;
            videoEl.setAttribute('autoplay', '');
            videoEl.setAttribute('muted', '');
            videoEl.setAttribute('loop', '');
            videoEl.setAttribute('playsinline', '');
            videoEl.preload     = 'auto'; 
            
            videoEl.style.opacity    = '0';
            videoEl.style.transition = 'opacity 0.6s ease-out';
            videoEl.style.zIndex     = '5';
            el.prepend(videoEl);
        } else {
            // Already present? Ensure basic properties are correct for CMS takeover
            if (DEBUG) console.log(`[CMS] Found pre-injected video, taking control...`);
            videoEl.style.opacity = '0';
            videoEl.style.transition = 'opacity 0.6s ease-out';
            videoEl.style.zIndex     = '5';
        }

        // Only update source if it's different to prevent reloading
        // We compare against the end of the URL to handle absolute vs relative paths cleanly
        const currentSrcObj = videoEl.querySelector('source') ? videoEl.querySelector('source').src : videoEl.src;
        
        const playableUrl = getPlayableVideoUrl(videoUrl);
        if ((!currentSrcObj || !currentSrcObj.endsWith(playableUrl.split('/').pop())) && playableUrl) {
            if (DEBUG) console.log(`[CMS] Updating video source to ${playableUrl}`);
            const sourceEl = videoEl.querySelector('source');
            if (sourceEl) {
                sourceEl.src = playableUrl;
            } else {
                videoEl.src = playableUrl;
            }
            videoEl.load();
        } else if (videoEl.readyState >= 3) {
            // Already buffered, trigger immediately
            if (DEBUG) console.log(`[CMS] Video already ready, skipping event listeners`);
            setTimeout(startVideo, 50);
        }

        // Force play and fade in as early as possible
        function startVideo() {
            if (videoEl.style.opacity === '1') return; // Already triggered
            if (DEBUG) console.log(`[CMS] Activating Video: ${videoUrl || videoEl.src}`);
            
            videoEl.play().then(() => {
                videoEl.style.opacity = '1';
                // Remove fallback image after fade completes to save resources
                setTimeout(() => { 
                    el.style.backgroundImage = 'none';
                }, 700);
            }).catch(e => {
                // If autoplay is blocked, we still want to show the frame if it's ready
                if (DEBUG) console.warn(`[CMS] Play blocked or failed:`, e);
                videoEl.style.opacity = '1';
            });
        }

        // Aggressive triggers: loadeddata often fires well before canplay
        videoEl.addEventListener('loadeddata', startVideo, { once: true });
        videoEl.addEventListener('canplay', startVideo, { once: true });
        videoEl.addEventListener('canplaythrough', startVideo, { once: true });
        videoEl.addEventListener('error', () => {
            if (DEBUG) console.warn('[CMS] Video failed to load; keeping fallback hero image');
            videoEl.style.opacity = '0';
            videoEl.pause();
            // Keep fallback background image visible
            el.style.backgroundImage = el.style.backgroundImage || '';
        }, { once: true });

        // Safety net: reduced to 1s if pre-injected
        setTimeout(() => {
            if (videoEl.style.opacity === '0') {
                if (DEBUG) console.log(`[CMS] Safety net (0.6s) triggered for video`);
                startVideo();
            }
        }, 600);
    }

    function applyHeroCloudflareEmbed(el, videoUrl) {
        const oldVideo = el.querySelector('video.cms-hero-video');
        if (oldVideo) oldVideo.remove();

        el.style.position = 'relative';
        el.style.overflow = 'hidden';
        const originalBgImage = el.style.backgroundImage || '';

        let iframeEl = el.querySelector('iframe.cms-hero-video');
        if (!iframeEl) {
            iframeEl = document.createElement('iframe');
            iframeEl.className = 'cms-hero-video absolute';
            iframeEl.setAttribute('frameborder', '0');
            iframeEl.setAttribute('allow', 'accelerometer; gyroscope; autoplay; encrypted-media; picture-in-picture;');
            iframeEl.setAttribute('allowfullscreen', '');
            iframeEl.style.position = 'absolute';
            iframeEl.style.top = '50%';
            iframeEl.style.left = '50%';
            iframeEl.style.transform = 'translate(-50%, -50%)';
            iframeEl.style.border = '0';
            iframeEl.style.display = 'block';
            iframeEl.loading = 'eager';
            iframeEl.style.opacity = '1';
            iframeEl.style.zIndex = '5';
            el.prepend(iframeEl);
        }

        const sizeIframeToCover = () => {
            const containerWidth = el.clientWidth || window.innerWidth || 1280;
            const containerHeight = el.clientHeight || window.innerHeight || 613;
            const containerAspect = containerWidth / containerHeight;
            let fittedWidth;
            let fittedHeight;

            if (containerAspect > HERO_VIDEO_ASPECT) {
                fittedWidth = containerWidth;
                fittedHeight = containerWidth / HERO_VIDEO_ASPECT;
            } else {
                fittedHeight = containerHeight;
                fittedWidth = containerHeight * HERO_VIDEO_ASPECT;
            }

            iframeEl.style.width = `${Math.ceil(fittedWidth)}px`;
            iframeEl.style.height = `${Math.ceil(fittedHeight)}px`;
        };

        const embedUrl = getCloudflareEmbedUrl(videoUrl);
        if (iframeEl.src !== embedUrl) {
            iframeEl.src = embedUrl;
        }

        sizeIframeToCover();
        window.addEventListener('resize', sizeIframeToCover);

        iframeEl.addEventListener('load', () => {
            sizeIframeToCover();
            const finalHeight = iframeEl.clientHeight || el.clientHeight;
            if (finalHeight > 0) {
                el.style.backgroundImage = 'none';
            } else if (originalBgImage) {
                el.style.backgroundImage = originalBgImage;
            }
        }, { once: true });
    }

    // Boot
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCMS);
    } else {
        initCMS();
    }

    function scheduleCmsSync() {
        if (cmsSyncTimer) clearTimeout(cmsSyncTimer);
        const interval = document.visibilityState === 'visible'
            ? CMS_VERSION_POLL_MS_ACTIVE
            : CMS_VERSION_POLL_MS_BACKGROUND;
        cmsSyncTimer = setTimeout(async () => {
            await checkCmsSyncVersion(false);
            scheduleCmsSync();
        }, interval);
    }

    // Keep public pages synced with near-instant active-tab refresh.
    scheduleCmsSync();
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            checkCmsSyncVersion(true);
        }
        scheduleCmsSync();
    });
    window.addEventListener('focus', () => checkCmsSyncVersion(true));

    // Instant sync signal from admin publish (same browser/session).
    window.addEventListener('storage', (event) => {
        if (event.key === 'chf_content_sync') {
            checkCmsSyncVersion(true);
        }
    });
    if ('BroadcastChannel' in window) {
        const syncChannel = new BroadcastChannel('chf-content-sync');
        syncChannel.addEventListener('message', () => checkCmsSyncVersion(true));
    }
})();
