/**
 * CHF Animation Core
 * Handles reveal-on-scroll logic using IntersectionObserver
 */

(function() {
    "use strict";

    const scrollReveal = {
        init: function() {
            this.setupObserver();
            this.handleLoad();
        },

        setupObserver: function() {
            const options = {
                root: null,
                rootMargin: '0px',
                threshold: 0.15 // Trigger when 15% of the element is visible
            };

            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const el = entry.target;
                        
                        // Use a slight timeout for staggered effect if requested via data-delay
                        const delay = el.getAttribute('data-delay') || 0;
                        
                        setTimeout(() => {
                            el.classList.add('revealed');
                        }, parseInt(delay));

                        // Unobserve once revealed to keep it revealed
                        observer.unobserve(el);
                    }
                });
            }, options);

            // Target all elements with .reveal class
            const revealElements = document.querySelectorAll('.reveal');
            revealElements.forEach(el => {
                observer.observe(el);
            });
        },

        handleLoad: function() {
            // Trigger an initial check for elements already in view
            window.addEventListener('load', () => {
                // The observer handles this naturally on first run
            });
        }
    };

    // Initialize on DOM content loaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => scrollReveal.init());
    } else {
        scrollReveal.init();
    }
})();
