/**
 * CHF Animation Core
 * Handles reveal-on-scroll logic using IntersectionObserver
 */

(function() {
    "use strict";

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const scrollReveal = {
        init: function() {
            this.setupObserver();
            // Force a check after a small delay to catch hero elements that might load via CMS
            setTimeout(() => this.checkManual(), 100);
            setTimeout(() => this.checkManual(), 500);
            setTimeout(() => this.checkManual(), 2000);
        },

        checkManual: function() {
            const revealElements = document.querySelectorAll('.reveal:not(.revealed)');
            revealElements.forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.top < window.innerHeight && rect.bottom > 0) {
                    el.classList.add('revealed');
                }
            });
        },

        setupObserver: function() {
            const options = {
                root: null,
                rootMargin: '0px',
                threshold: 0.01 // Very sensitive to catch even a sliver of content
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
        }
    };

    const premiumInteractions = {
        init: function() {
            this.setActiveNavState();
            this.enhanceMobileMenu();
            if (!prefersReducedMotion) {
                this.setupDepthParallax();
                this.setupCardTilt();
            }
        },

        setActiveNavState: function() {
            const path = window.location.pathname.replace(/\/$/, "");
            const slug = path.split("/").pop() || "index";
            const navLinks = document.querySelectorAll("nav a[href]");

            navLinks.forEach((link) => {
                const href = (link.getAttribute("href") || "").replace(/\/$/, "");
                if (!href || href.startsWith("http") || href.startsWith("javascript:")) return;
                if (href === slug || (slug === "index" && href === "/")) {
                    link.classList.add("text-accent-bronze");
                    link.classList.remove("text-ivory-dim");
                }
            });
        },

        enhanceMobileMenu: function() {
            const mobileMenu = document.getElementById("mobile-menu");
            if (!mobileMenu) return;

            const body = document.body;
            const watcher = new MutationObserver(() => {
                const opened = mobileMenu.classList.contains("opacity-100");
                mobileMenu.classList.toggle("menu-open", opened);
                body.classList.toggle("menu-open", opened);
            });

            watcher.observe(mobileMenu, {
                attributes: true,
                attributeFilter: ["class"]
            });
        },

        setupDepthParallax: function() {
            const hero = document.querySelector(".hero-section");
            if (!hero) return;

            const media = hero.querySelector("[data-cms='home/hero/image'], .cms-hero-video");
            if (!media) return;

            const onScroll = () => {
                const offset = Math.min(window.scrollY * 0.16, 40);
                media.style.transform = media.classList.contains("cms-hero-video")
                    ? "translate(-50%, calc(-50% + " + offset + "px)) scale(1.03)"
                    : "translateY(" + offset + "px) scale(1.04)";
            };

            onScroll();
            window.addEventListener("scroll", onScroll, { passive: true });
        },

        setupCardTilt: function() {
            const cards = document.querySelectorAll(".service-card, .premium-hover-img");
            if (!cards.length) return;

            cards.forEach((card) => {
                card.addEventListener("pointermove", (event) => {
                    const rect = card.getBoundingClientRect();
                    const px = (event.clientX - rect.left) / rect.width;
                    const py = (event.clientY - rect.top) / rect.height;
                    const rx = (0.5 - py) * 5;
                    const ry = (px - 0.5) * 7;

                    card.style.transform = "perspective(900px) rotateX(" + rx.toFixed(2) + "deg) rotateY(" + ry.toFixed(2) + "deg) translateY(-4px)";
                    card.style.boxShadow = "0 18px 42px rgba(0, 0, 0, 0.35)";
                });

                card.addEventListener("pointerleave", () => {
                    card.style.transform = "";
                    card.style.boxShadow = "";
                });
            });
        }
    };

    // Initialize on DOM content loaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            scrollReveal.init();
            premiumInteractions.init();
        });
    } else {
        scrollReveal.init();
        premiumInteractions.init();
    }
})();
