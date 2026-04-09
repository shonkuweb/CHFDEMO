/**
 * CHF Content Loader
 * Dynamically loads page content from JSON data files.
 * Falls back gracefully to the hardcoded HTML if JSON is unavailable.
 */
(function() {
    'use strict';

    // Determine the current page's slug from the filename
    const path = window.location.pathname;
    const filename = path.split('/').pop().replace('.html', '');
    
    const VALID_PAGES = [
        'full-grown-avenue-trees',
        'exotic-indoor-plants',
        'bonsai',
        'curated-plants'
    ];

    if (!VALID_PAGES.includes(filename)) return;

    // Fetch and render content from high-performance DB API
    fetch(`/api/data?slug=${filename}`)
        .then(res => {
            if (!res.ok) throw new Error('Not found');
            return res.json();
        })
        .then(data => {
            renderHero(data.page);
            renderCategories(data.categories);
        })
        .catch(() => {
            // Silently fail — hardcoded HTML remains
            console.log('[CHF] Using static content (JSON not available)');
        });

    function renderHero(page) {
        // Update the hero section
        const heroSection = document.querySelector('main .max-w-7xl');
        if (!heroSection) return;

        const heroContent = heroSection.querySelector('.max-w-3xl');
        if (!heroContent) return;

        // Update breadcrumb if it exists
        const breadcrumb = heroContent.querySelector('.text-accent-bronze.text-\\[10px\\]');
        if (breadcrumb && page.breadcrumb) {
            breadcrumb.textContent = page.breadcrumb;
        }

        // Update title
        const h2 = heroContent.querySelector('h2');
        if (h2) {
            h2.innerHTML = `
                ${escHtml(page.titleLine1)} <br />
                <span class="text-accent-bronze italic font-light drop-shadow-sm">${escHtml(page.titleLine2)}</span>
            `;
        }

        // Update subtitle
        const subtitle = heroSection.querySelector('.text-gray-400');
        if (subtitle && page.subtitle) {
            subtitle.textContent = page.subtitle;
        }
    }

    function renderCategories(categories) {
        const container = document.querySelector('.flex.flex-col.gap-32');
        if (!container) return;

        container.innerHTML = categories.map((cat, i) => {
            const isReversed = i % 2 === 1;
            const mediaUrl = cat.image || '';
            const isVideo = mediaUrl.split('?')[0].split('.').pop().toLowerCase().match(/(mp4|webm|mov|ogg)/);
            
            return `
                <!-- ${cat.label} -->
                <div class="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
                    <div class="lg:col-span-7 ${isReversed ? 'lg:order-2' : ''}">
                        <div class="relative aspect-video overflow-hidden bg-surface-dark">
                            ${mediaUrl.length > 0 
                                ? (isVideo 
                                    ? `<video src="${mediaUrl}" class="w-full h-full object-cover transition-transform duration-[2s] hover:scale-110" autoplay muted loop playsinline></video>`
                                    : `<img src="${mediaUrl}" alt="${escHtml(cat.title)}" class="w-full h-full object-cover transition-transform duration-[2s] hover:scale-110" />`)
                                : `<div class="w-full h-full transition-transform duration-[2s] hover:scale-110 bg-[#1a1a1a] wireframe-cross"></div>`
                            }
                        </div>
                    </div>
                    <div class="lg:col-span-5 ${isReversed ? 'lg:pr-12 lg:order-1 text-right lg:text-left' : 'lg:pl-12'}">
                        <span class="text-[10px] uppercase tracking-widest text-accent-bronze font-bold block mb-4">${escHtml(cat.label)}</span>
                        <h3 class="font-serif text-4xl mb-6">${escHtml(cat.title)}</h3>
                        <p class="text-ivory-dim font-light leading-relaxed mb-8">
                            ${escHtml(cat.description)}
                        </p>
                        <a href="${escHtml(cat.ctaLink)}" class="inline-flex items-center gap-3 text-xs uppercase tracking-widest border-b border-accent-bronze pb-1 hover:text-accent-bronze transition-colors">${escHtml(cat.ctaText)}</a>
                    </div>
                </div>
            `;
        }).join('');
    }

    function escHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
})();
