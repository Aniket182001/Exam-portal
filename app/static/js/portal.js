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
