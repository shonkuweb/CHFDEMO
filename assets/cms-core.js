/**
 * CHF Universal CMS Core
 * Standardizes content loading across all site pages
 */
(function() {
    const DEBUG = true;

    async function initCMS() {
        // 1. Identify current page slug
        const path = window.location.pathname;
        const page = path.split('/').pop().replace('.html', '') || 'index';
        
        if (DEBUG) console.log(`[CMS] Initializing for page: ${page}`);

        try {
            // 2. Fetch page-specific and global content in parallel
            const [pageRes, globalRes] = await Promise.all([
                fetch(`/api/site-content?page=${page}`),
                fetch(`/api/site-content?page=global`)
            ]);

            const pageData = await pageRes.json();
            const globalData = await globalRes.json();
            
            // Merge content (page content overrides global in case of collision)
            const cmsData = { ...globalData, ...pageData };

            if (DEBUG) console.log(`[CMS] Content loaded:`, cmsData);

            // 3. Apply content to [data-cms] elements
            applyContent(cmsData);

        } catch (err) {
            console.error('[CMS] Failed to initialize:', err);
        }
    }

    function applyContent(data) {
        const elements = document.querySelectorAll('[data-cms]');
        
        elements.forEach(el => {
            const path = el.getAttribute('data-cms');
            const content = data[path];

            if (!content) {
                if (DEBUG) console.warn(`[CMS] No data found for path: ${path}`);
                return;
            }

            const val = content.value;
            const type = content.type;

            // Handle different element types
            if (type === 'media') {
                if (el.tagName === 'IMG') {
                    el.src = val;
                } else if (el.tagName === 'VIDEO') {
                    el.src = val;
                } else {
                    // Fallback: apply as background image
                    el.style.backgroundImage = `url('${val}')`;
                }
            } else {
                // Default to text/html injection
                el.innerHTML = val;
            }
        });
    }

    // Run on boot
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCMS);
    } else {
        initCMS();
    }
})();
