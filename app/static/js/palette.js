/**
 * Phase 3.1: Smart Admin Workspace - Command Palette
 * Inspired by Linear & Notion
 */

document.addEventListener('DOMContentLoaded', () => {
    const backdrop = document.getElementById('aiqm-command-palette');
    const input = document.getElementById('palette-search-input');
    const resultsContainer = document.getElementById('palette-results-container');
    
    if (!backdrop || !input || !resultsContainer) return;

    let isOpen = false;
    let selectedIndex = -1;
    let currentResults = [];

    // --- Data Dictionary ---
    const GLOBAL_PAGES = [
        { title: 'Admin Dashboard', url: '/admin/exams', icon: 'bi-speedometer2', group: 'Pages' },
        { title: 'Create New Exam', url: '/admin/exams/create', icon: 'bi-plus-circle', group: 'Pages' },
        { title: 'Email Center', url: '/admin/email', icon: 'bi-envelope-paper', group: 'Pages' }
    ];

    const GLOBAL_ACTIONS = [
        { title: 'View All Exams', url: '/admin/exams', icon: 'bi-journal-text', group: 'Actions' },
        { title: 'Go to Home', url: '/', icon: 'bi-house', group: 'Actions' }
    ];

    // Read from LocalStorage
    let recentPages = JSON.parse(localStorage.getItem('aiqm_recent_pages')) || [];
    let favoriteExams = JSON.parse(localStorage.getItem('aiqm_favorite_exams')) || [];

    // Log current page to recent (limit 5)
    function logCurrentPage() {
        const title = document.title.replace(' - AIQM Exam Portal', '').trim();
        const url = window.location.pathname + window.location.search;
        
        // Don't log if it's identical to the most recent one
        if (recentPages.length > 0 && recentPages[0].url === url) return;

        // Remove exact duplicate if it exists elsewhere
        recentPages = recentPages.filter(p => p.url !== url);
        
        recentPages.unshift({ title, url, icon: 'bi-clock-history', group: 'Recent' });
        
        if (recentPages.length > 5) {
            recentPages.pop();
        }
        localStorage.setItem('aiqm_recent_pages', JSON.stringify(recentPages));
    }
    logCurrentPage();

    // --- Search Engine ---
    function fuzzySearch(query, items) {
        if (!query) return items;
        const q = query.toLowerCase();
        return items.filter(item => item.title.toLowerCase().includes(q));
    }

    function renderResults(query = '') {
        resultsContainer.innerHTML = '';
        currentResults = [];
        selectedIndex = -1;

        const allItems = [];

        // If no query, show Favorites and Recent
        if (!query) {
            if (favoriteExams.length > 0) {
                allItems.push(...favoriteExams.map(f => ({ ...f, group: 'Favorites' })));
            }
            if (recentPages.length > 0) {
                allItems.push(...recentPages);
            }
        }

        // Always search Pages and Actions if there is a query
        if (query) {
            allItems.push(...GLOBAL_PAGES, ...GLOBAL_ACTIONS, ...favoriteExams, ...recentPages);
        } else if (allItems.length === 0) {
            // Default empty state suggestions
            allItems.push(...GLOBAL_PAGES);
        }

        // Deduplicate by URL
        const uniqueItemsMap = new Map();
        allItems.forEach(item => {
            if (!uniqueItemsMap.has(item.url)) {
                uniqueItemsMap.set(item.url, item);
            }
        });
        const uniqueItems = Array.from(uniqueItemsMap.values());

        const filtered = fuzzySearch(query, uniqueItems);

        if (filtered.length === 0) {
            resultsContainer.innerHTML = `
                <div class="text-center py-4 text-muted">
                    <i class="bi bi-search fs-3 mb-2 d-block"></i>
                    <p class="mb-0">No results found for "${query}"</p>
                </div>
            `;
            return;
        }

        // Group results
        const groups = {};
        filtered.forEach(item => {
            if (!groups[item.group]) groups[item.group] = [];
            groups[item.group].push(item);
        });

        // Render groups
        for (const [groupName, items] of Object.entries(groups)) {
            const groupHeader = document.createElement('div');
            groupHeader.className = 'aiqm-palette-group';
            groupHeader.textContent = groupName;
            resultsContainer.appendChild(groupHeader);

            items.forEach(item => {
                const index = currentResults.length;
                currentResults.push(item);

                const el = document.createElement('a');
                el.href = item.url;
                el.className = 'aiqm-palette-item';
                el.dataset.index = index;
                el.innerHTML = `
                    <i class="bi ${item.icon || 'bi-file-earmark'}"></i>
                    <span class="aiqm-palette-item-text">${item.title}</span>
                    ${item.group === 'Pages' || item.group === 'Actions' ? '<span class="aiqm-palette-item-hint">Action</span>' : ''}
                `;
                
                el.addEventListener('mouseenter', () => {
                    updateSelection(index);
                });

                resultsContainer.appendChild(el);
            });
        }
        
        if (currentResults.length > 0) {
            updateSelection(0);
        }
    }

    // --- State Management ---
    function openPalette() {
        isOpen = true;
        backdrop.classList.add('show');
        input.value = '';
        renderResults();
        setTimeout(() => input.focus(), 100);
    }

    function closePalette() {
        isOpen = false;
        backdrop.classList.remove('show');
        input.blur();
    }

    function updateSelection(index) {
        if (currentResults.length === 0) return;
        
        // Wrap around
        if (index < 0) index = currentResults.length - 1;
        if (index >= currentResults.length) index = 0;
        
        selectedIndex = index;
        
        const items = resultsContainer.querySelectorAll('.aiqm-palette-item');
        items.forEach((item, i) => {
            if (i === selectedIndex) {
                item.classList.add('active');
                item.scrollIntoView({ block: 'nearest' });
            } else {
                item.classList.remove('active');
            }
        });
    }

    // --- Event Listeners ---
    document.addEventListener('keydown', (e) => {
        // Ctrl+K to open
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            if (isOpen) closePalette();
            else openPalette();
        }

        // Close on Esc
        if (e.key === 'Escape' && isOpen) {
            e.preventDefault();
            closePalette();
        }
    });

    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) closePalette();
    });

    input.addEventListener('input', (e) => {
        renderResults(e.target.value);
    });

    input.addEventListener('keydown', (e) => {
        if (!isOpen) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            updateSelection(selectedIndex + 1);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            updateSelection(selectedIndex - 1);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (selectedIndex >= 0 && currentResults[selectedIndex]) {
                window.location.href = currentResults[selectedIndex].url;
            }
        }
    });
    
    // Add Star toggle for Favorites on Exam List
    // We will attach a global listener to watch for clicks on a generic `.star-exam` button
    document.addEventListener('click', (e) => {
        const starBtn = e.target.closest('.star-exam');
        if (!starBtn) return;
        
        e.preventDefault();
        const examId = starBtn.dataset.examId;
        const examTitle = starBtn.dataset.examTitle;
        const examUrl = starBtn.dataset.examUrl;
        
        const existingIndex = favoriteExams.findIndex(f => f.url === examUrl);
        if (existingIndex >= 0) {
            favoriteExams.splice(existingIndex, 1);
            starBtn.innerHTML = '<i class="bi bi-star"></i>';
            if(window.showToast) window.showToast('Removed from favorites', 'info');
        } else {
            favoriteExams.push({ title: examTitle, url: examUrl, icon: 'bi-star-fill', group: 'Favorites' });
            starBtn.innerHTML = '<i class="bi bi-star-fill text-warning"></i>';
            if(window.showToast) window.showToast('Added to favorites', 'success');
        }
        localStorage.setItem('aiqm_favorite_exams', JSON.stringify(favoriteExams));
    });

    // Initialize Favorites stars on load
    const starBtns = document.querySelectorAll('.star-exam');
    starBtns.forEach(btn => {
        const url = btn.dataset.examUrl;
        if (favoriteExams.some(f => f.url === url)) {
            btn.innerHTML = '<i class="bi bi-star-fill text-warning"></i>';
        }
    });
});
