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
    let toast = document.getElementById('aiqmGlobalToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'aiqmGlobalToast';
        toast.className = 'aiqm-toast apple-toast';
        document.body.appendChild(toast);
    }
    
    // Set Icon based on type
    let iconClass = "bi-check-circle-fill text-success";
    if (type === "danger") iconClass = "bi-exclamation-triangle-fill text-danger";
    if (type === "warning") iconClass = "bi-exclamation-circle-fill text-warning";
    if (type === "info") iconClass = "bi-info-circle-fill text-info";

    toast.innerHTML = `<i class="bi ${iconClass} fs-5"></i> <span class="toast-text">${message}</span>`;
    
    // Reset state for animations
    toast.classList.remove('show');
    
    // Trigger reflow to restart animation
    void toast.offsetWidth;
    
    setTimeout(() => {
        toast.classList.add('show');
    }, 10);
    
    if (window.aiqmToastTimeout) {
        clearTimeout(window.aiqmToastTimeout);
    }
    
    window.aiqmToastTimeout = setTimeout(() => {
        toast.classList.remove('show');
    }, 2000); // 2 second auto-dismiss per requirement
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
