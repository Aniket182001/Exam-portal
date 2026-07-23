/**
 * AIQM Exam Portal - Global Productivity Utilities
 * Phase 2.6 Implementation
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Instant Search (Debounce)
    const searchInputs = document.querySelectorAll('input[name="search"], input[type="search"]');
    searchInputs.forEach(input => {
        let debounceTimer;
        input.addEventListener('input', function() {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                const form = this.closest('form');
                if (form) {
                    form.submit();
                }
            }, 300);
        });
    });

    // 2. Keyboard Shortcuts
    document.addEventListener('keydown', (e) => {
        // Allow default behavior if user is typing in an input (except for specific shortcuts)
        const isInput = e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT';

        // Shortcut: "/" to focus search
        if (e.key === '/' && !isInput) {
            const primarySearch = document.querySelector('input[name="search"], input[type="search"]');
            if (primarySearch) {
                e.preventDefault();
                primarySearch.focus();
                // Move cursor to the end
                const val = primarySearch.value;
                primarySearch.value = '';
                primarySearch.value = val;
            }
        }

        // Shortcut: "Ctrl + Enter" or "Ctrl + S" to save/submit
        if ((e.ctrlKey || e.metaKey) && (e.key === 'Enter' || e.key.toLowerCase() === 's')) {
            const form = e.target.closest('form') || document.querySelector('form');
            if (form) {
                e.preventDefault();
                // Find primary submit button to trigger loading states if they exist
                const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
                if (submitBtn) {
                    submitBtn.click();
                } else {
                    form.submit();
                }
            }
        }
    });
});

/**
 * Global AIQM Toast Notification Helper
 * Replaces intrusive browser alerts for non-critical information.
 * 
 * @param {string} message - The message to display
 * @param {string} type - "success", "danger", "warning", or "info"
 */
window.showToast = function(message, type = "success") {
    let container = document.querySelector('.aiqm-toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'aiqm-toast-container';
        container.setAttribute('aria-live', 'polite');
        container.setAttribute('aria-atomic', 'true');
        document.body.appendChild(container);
    }
    
    // Set Icon based on type
    let iconClass = "bi-check";
    if (type === "danger") iconClass = "bi-exclamation-lg";
    if (type === "warning") iconClass = "bi-exclamation-triangle";
    if (type === "info") iconClass = "bi-info-lg";

    const toast = document.createElement('div');
    toast.className = `aiqm-toast aiqm-toast-${type}`;
    toast.setAttribute('role', 'alert');
    
    toast.innerHTML = `
        <div class="aiqm-toast-icon-circle">
            <i class="bi ${iconClass}"></i>
        </div>
        <div class="aiqm-toast-content">
            <span class="aiqm-toast-message">${message}</span>
        </div>
        <button type="button" class="aiqm-toast-close" aria-label="Close">
            <i class="bi bi-x"></i>
        </button>
    `;
    
    // Auto-dismiss after 5 seconds
    const timeout = setTimeout(() => {
        closeToast(toast);
    }, 5000);
    
    // Setup close button
    const closeBtn = toast.querySelector('.aiqm-toast-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            clearTimeout(timeout);
            closeToast(toast);
        });
    }
    
    // Prepend so newest is on top
    container.prepend(toast);
};

// 3. Global Modal Focus Management (Phase 2.5)
document.addEventListener('shown.bs.modal', function (event) {
    const modal = event.target;
    // Find first autofocus element, or fallback to first visible input
    const focusable = modal.querySelector('[autofocus]') || 
                      modal.querySelector('input:not([type="hidden"]):not([disabled]), textarea:not([disabled]), select:not([disabled])');
    if (focusable) {
        focusable.focus();
    }
});

// 4. Global Keyboard Shortcuts (Phase 3.1)
document.addEventListener('keydown', function(e) {
    // Ignore if typing in an input/textarea
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
        return;
    }

    // Press '/' to focus search
    if (e.key === '/') {
        e.preventDefault();
        const searchInput = document.querySelector('input[type="search"], input[name="search"]');
        if (searchInput) {
            searchInput.focus();
            // Move cursor to end
            const val = searchInput.value;
            searchInput.value = '';
            searchInput.value = val;
        }
    }
});

// 5. Global Toast Notifications (Server-rendered Flask Flash Messages)
document.addEventListener('DOMContentLoaded', () => {
    const flashToasts = document.querySelectorAll('.aiqm-toast');
    flashToasts.forEach(toast => {
        // Auto-dismiss after 5 seconds
        const timeout = setTimeout(() => {
            closeToast(toast);
        }, 5000);
        
        // Setup close button
        const closeBtn = toast.querySelector('.aiqm-toast-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                clearTimeout(timeout);
                closeToast(toast);
            });
        }
    });
});

window.closeToast = function(toastElement) {
    if (!toastElement) return;
    toastElement.classList.add('toast-hiding');
    setTimeout(() => {
        toastElement.remove();
        // Remove container if empty
        const container = document.querySelector('.aiqm-toast-container');
        if (container && container.children.length === 0) {
            // we leave it, it's invisible anyway, or remove it. Better leave it.
        }
    }, 300); // Wait for CSS transition
};

/* ================================================================
   HERO CANVAS PARTICLE MOTION (Isolated Premium Background Motion)
   ================================================================ */
(function initHeroMotion() {
    function setupHeroCanvas() {
        const heroSection = document.getElementById('heroSection');
        const canvas = document.getElementById('heroCanvas');
        if (!heroSection || !canvas) return;

        // Respect prefers-reduced-motion
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            return;
        }

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        let width = 0;
        let height = 0;
        let dpr = 1;

        function resizeCanvas() {
            width = heroSection.offsetWidth;
            height = heroSection.offsetHeight;
            dpr = Math.min(window.devicePixelRatio || 1, 2);
            canvas.width = width * dpr;
            canvas.height = height * dpr;
            ctx.scale(dpr, dpr);
        }

        resizeCanvas();

        let resizeTimeout;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(resizeCanvas, 150);
        }, { passive: true });

        // Mouse Position tracking inside Hero Section
        const mouse = {
            x: width / 2,
            y: height / 2,
            active: false,
            currentAlpha: 0
        };

        heroSection.addEventListener('mousemove', (e) => {
            const rect = heroSection.getBoundingClientRect();
            mouse.x = e.clientX - rect.left;
            mouse.y = e.clientY - rect.top;
            mouse.active = true;
        }, { passive: true });

        heroSection.addEventListener('mouseleave', () => {
            mouse.active = false;
        }, { passive: true });

        // Particles Configuration (26 particles: 22-28 range requirement)
        const particleCount = 26;
        const particles = [];

        for (let i = 0; i < particleCount; i++) {
            particles.push({
                x: Math.random() * width,
                y: Math.random() * height,
                vx: (Math.random() - 0.5) * 0.45,
                vy: (Math.random() - 0.5) * 0.45,
                radius: Math.random() * 1.2 + 1.3,
                baseAlpha: Math.random() * 0.25 + 0.25
            });
        }

        let animationFrameId = null;
        let isAnimating = false;
        let isHeroVisible = true;

        function render() {
            ctx.clearRect(0, 0, width, height);

            // Smooth fade for mouse interaction
            const targetMouseAlpha = mouse.active ? 1 : 0;
            mouse.currentAlpha += (targetMouseAlpha - mouse.currentAlpha) * 0.08;

            for (let i = 0; i < particleCount; i++) {
                const p = particles[i];

                p.x += p.vx;
                p.y += p.vy;

                // Bounce off boundaries softly
                if (p.x < 0) { p.x = 0; p.vx *= -1; }
                if (p.x > width) { p.x = width; p.vx *= -1; }
                if (p.y < 0) { p.y = 0; p.vy *= -1; }
                if (p.y > height) { p.y = height; p.vy *= -1; }

                // Check mouse proximity
                let mouseDist = 999;
                let mouseGlow = 0;
                if (mouse.currentAlpha > 0.001) {
                    const mdx = mouse.x - p.x;
                    const mdy = mouse.y - p.y;
                    mouseDist = Math.sqrt(mdx * mdx + mdy * mdy);
                    if (mouseDist < 140) {
                        mouseGlow = (1 - mouseDist / 140) * mouse.currentAlpha;
                    }
                }

                // Draw Particle
                const currentRadius = p.radius + mouseGlow * 1.2;
                const currentAlpha = Math.min(0.85, p.baseAlpha + mouseGlow * 0.4);

                ctx.beginPath();
                ctx.arc(p.x, p.y, currentRadius, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(249, 115, 22, ${currentAlpha})`;
                ctx.fill();

                // Mouse Connection Lines
                if (mouseGlow > 0.01) {
                    ctx.beginPath();
                    ctx.moveTo(p.x, p.y);
                    ctx.lineTo(mouse.x, mouse.y);
                    ctx.strokeStyle = `rgba(234, 88, 12, ${0.35 * mouseGlow})`;
                    ctx.lineWidth = 1.0;
                    ctx.stroke();
                }

                // Inter-particle Connection Lines
                for (let j = i + 1; j < particleCount; j++) {
                    const p2 = particles[j];
                    const dx = p2.x - p.x;
                    const dy = p2.y - p.y;
                    const dist = Math.sqrt(dx * dx + dy * dy);

                    if (dist < 110) {
                        const lineAlpha = (1 - dist / 110) * 0.14;
                        ctx.beginPath();
                        ctx.moveTo(p.x, p.y);
                        ctx.lineTo(p2.x, p2.y);
                        ctx.strokeStyle = `rgba(249, 115, 22, ${lineAlpha})`;
                        ctx.lineWidth = 0.75;
                        ctx.stroke();
                    }
                }
            }

            if (isAnimating) {
                animationFrameId = requestAnimationFrame(render);
            }
        }

        function startAnimation() {
            if (!isAnimating && isHeroVisible && !document.hidden) {
                isAnimating = true;
                animationFrameId = requestAnimationFrame(render);
            }
        }

        function stopAnimation() {
            if (isAnimating) {
                isAnimating = false;
                if (animationFrameId) {
                    cancelAnimationFrame(animationFrameId);
                    animationFrameId = null;
                }
            }
        }

        // Pause when tab is hidden
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                stopAnimation();
            } else {
                startAnimation();
            }
        });

        // Pause when scrolled out of view using IntersectionObserver
        if ('IntersectionObserver' in window) {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    isHeroVisible = entry.isIntersecting;
                    if (isHeroVisible) {
                        startAnimation();
                    } else {
                        stopAnimation();
                    }
                });
            }, { threshold: 0 });
            observer.observe(heroSection);
        } else {
            startAnimation();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupHeroCanvas);
    } else {
        setupHeroCanvas();
    }
})();
