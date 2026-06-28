/**
 * Phase 3.2: Bulk Operations & Smart Multi-Selection
 * Provides Gmail-style shift-click selection and a Floating Action Bar.
 */

document.addEventListener('DOMContentLoaded', () => {
    const table = document.querySelector('table.table');
    if (!table) return; // Only run on pages with tables

    const selectAllCheckbox = document.getElementById('selectAll');
    const rowCheckboxes = Array.from(table.querySelectorAll('tbody .form-check-input'));
    
    if (rowCheckboxes.length === 0) return; // No selectable rows

    const bulkBar = document.getElementById('aiqm-bulk-bar');
    const bulkCountText = document.getElementById('aiqm-bulk-count-text');
    const bulkActionsContainer = document.getElementById('aiqm-bulk-actions');
    const bulkCloseBtn = document.getElementById('aiqm-bulk-close');
    
    let lastCheckedIndex = -1;
    let selectedCount = 0;

    // --- Core Selection Logic ---
    function updateSelectionState() {
        selectedCount = rowCheckboxes.filter(cb => cb.checked).length;
        
        // Highlight rows
        rowCheckboxes.forEach(cb => {
            const tr = cb.closest('tr');
            if (cb.checked) {
                tr.classList.add('selected-row');
            } else {
                tr.classList.remove('selected-row');
            }
        });

        // Update Select All checkbox state
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = selectedCount > 0 && selectedCount === rowCheckboxes.length;
            selectAllCheckbox.indeterminate = selectedCount > 0 && selectedCount < rowCheckboxes.length;
        }

        // Update Floating Bar
        if (bulkBar && bulkCountText) {
            if (selectedCount > 0) {
                bulkCountText.textContent = `${selectedCount} selected`;
                bulkBar.classList.add('show');
                populateDynamicActions();
            } else {
                bulkBar.classList.remove('show');
            }
        }
    }

    // --- Shift-Click Engine ---
    rowCheckboxes.forEach((checkbox, index) => {
        checkbox.addEventListener('click', (e) => {
            if (e.shiftKey && lastCheckedIndex !== -1) {
                const start = Math.min(index, lastCheckedIndex);
                const end = Math.max(index, lastCheckedIndex);
                
                // Toggle the range to match the target checkbox state
                const targetState = checkbox.checked;
                
                for (let i = start; i <= end; i++) {
                    rowCheckboxes[i].checked = targetState;
                }
                
                // Keep text selection from happening while shift clicking
                document.getSelection().removeAllRanges();
            }
            
            lastCheckedIndex = index;
            updateSelectionState();
        });
    });

    // --- Select All Logic ---
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', (e) => {
            const isChecked = e.target.checked;
            rowCheckboxes.forEach(cb => cb.checked = isChecked);
            lastCheckedIndex = -1; // Reset range anchor
            updateSelectionState();
        });
    }

    // --- Clear Selection ---
    function clearSelection() {
        rowCheckboxes.forEach(cb => cb.checked = false);
        lastCheckedIndex = -1;
        updateSelectionState();
    }

    if (bulkCloseBtn) {
        bulkCloseBtn.addEventListener('click', clearSelection);
    }

    // --- Dynamic Action Mapping ---
    // Clones `.action-btn` elements from the page toolbar into the floating bar
    function populateDynamicActions() {
        if (!bulkActionsContainer) return;
        bulkActionsContainer.innerHTML = '';
        
        const pageActions = document.querySelectorAll('.admin-toolbar .action-btn');
        pageActions.forEach(action => {
            const clone = action.cloneNode(true);
            clone.classList.remove('d-none'); // Ensure it's visible in the floating bar
            
            // Re-bind the click to trigger the original hidden action button
            clone.addEventListener('click', (e) => {
                e.preventDefault(); // Prevent direct form submission on clone
                action.click(); // Trigger the real button
            });
            
            bulkActionsContainer.appendChild(clone);
        });
    }

    // --- Keyboard Shortcuts (Ctrl+A, Esc) ---
    document.addEventListener('keydown', (e) => {
        // Ignore if typing in an input/textarea
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
            return;
        }

        // Esc to clear selection
        if (e.key === 'Escape' && selectedCount > 0) {
            clearSelection();
        }

        // Ctrl+A to Select All visible
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
            e.preventDefault();
            if (selectAllCheckbox) {
                selectAllCheckbox.click(); // Programmatically click to ensure events fire properly
            }
        }
    });

    // --- Filter Interception ---
    // Warn user if they try to filter/search while they have active selections
    const searchForms = document.querySelectorAll('form[method="GET"]');
    searchForms.forEach(form => {
        form.addEventListener('submit', (e) => {
            if (selectedCount > 0) {
                // If they have selections, we clear them before submitting
                // Alternatively, we could prevent submission and warn.
                if(window.showToast) window.showToast('Filtering cleared your current selection.', 'warning');
                clearSelection();
            }
        });
    });

    // Initialize state on load
    updateSelectionState();
});
