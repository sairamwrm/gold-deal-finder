/* Gold Deal Finder refresh */
(function () {
    const DEFAULT_FILTERS = Object.freeze({
        source: '',
        purity: '',
        search: '',
        min_discount: -100,
        max_discount: 100,
        min_weight: 0,
        max_weight: 100,
        onlyFavorites: false,
    });

    function cloneFilters() {
        return JSON.parse(JSON.stringify(DEFAULT_FILTERS));
    }

    function safeArray(value) {
        return Array.isArray(value) ? value : [];
    }

    function numeric(value, fallback = 0) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    window.app = new Vue({
        el: '#app',

        data: {
            activeTab: 'products',
            loading: true,
            loadingProducts: false,
            refreshing: false,
            scanning: false,
            bootError: '',

            darkMode: localStorage.getItem('goldDarkMode') === 'true',
            windowWidth: window.innerWidth,
            mobileMenuOpen: false,
            showMobileFilters: false,
            showShortcuts: false,

            showScanModal: false,
            showExportModal: false,
            showFavoritesModal: false,
            selectedProduct: null,

            selectedScanId: null,
            selectedScanTimestamp: null,
            selectedScanIsLatest: true,
            latestScanId: null,
            latestScanTimestamp: null,

            allProducts: [],
            scans: [],
            summaryStats: {
                live: {},
                historical: {},
            },
            spotPrice: null,
            timeline: {
                timeline: {},
                total_scans: 0,
                total_products: 0,
            },

            filters: cloneFilters(),
            currentPage: 1,
            itemsPerPage: 12,
            pageSizeOptions: [12, 24, 48],
            sortBy: 'discount_percent',
            sortOrder: 'desc',

            favorites: JSON.parse(localStorage.getItem('goldFavorites') || '[]'),
            exportFormat: 'csv',

            notifications: [],
            notificationId: 0,

            distributionChart: null,
            scanTrendChart: null,

            shortcuts: [
                { key: 'Ctrl/Cmd + F', action: 'Focus search' },
                { key: 'Ctrl/Cmd + R', action: 'Refresh dashboard' },
                { key: 'Ctrl/Cmd + N', action: 'Open scan dialog' },
                { key: 'Ctrl/Cmd + D', action: 'Toggle theme' },
                { key: 'Esc', action: 'Close overlays' },
            ],
        },

        computed: {
            filteredProducts() {
                let products = [...this.allProducts];

                if (this.filters.source) {
                    products = products.filter((product) => product.source === this.filters.source);
                }
                if (this.filters.purity) {
                    products = products.filter((product) => product.purity === this.filters.purity);
                }
                if (this.filters.search) {
                    const term = this.filters.search.toLowerCase();
                    products = products.filter((product) => {
                        return [product.title, product.brand, product.source, product.purity]
                            .filter(Boolean)
                            .some((value) => String(value).toLowerCase().includes(term));
                    });
                }

                products = products.filter((product) => {
                    const discount = numeric(product.discount_percent);
                    const weight = numeric(product.weight_grams);
                    return (
                        discount >= this.filters.min_discount &&
                        discount <= this.filters.max_discount &&
                        weight >= this.filters.min_weight &&
                        weight <= this.filters.max_weight
                    );
                });

                if (this.filters.onlyFavorites) {
                    products = products.filter((product) => this.favorites.includes(product.url));
                }

                return products;
            },

            sortedProducts() {
                const products = [...this.filteredProducts];
                const direction = this.sortOrder === 'desc' ? -1 : 1;
                products.sort((left, right) => {
                    let a = left[this.sortBy];
                    let b = right[this.sortBy];

                    if (this.sortBy === 'timestamp') {
                        a = new Date(a || 0).getTime();
                        b = new Date(b || 0).getTime();
                    } else {
                        a = typeof a === 'string' ? a.toLowerCase() : numeric(a);
                        b = typeof b === 'string' ? b.toLowerCase() : numeric(b);
                    }

                    if (a < b) return -1 * direction;
                    if (a > b) return 1 * direction;
                    return 0;
                });
                return products;
            },

            paginatedProducts() {
                const start = (this.currentPage - 1) * this.itemsPerPage;
                return this.sortedProducts.slice(start, start + this.itemsPerPage);
            },

            totalPages() {
                return Math.max(1, Math.ceil(this.sortedProducts.length / this.itemsPerPage));
            },

            pageNumbers() {
                const total = this.totalPages;
                const current = this.currentPage;
                const start = Math.max(1, current - 2);
                const end = Math.min(total, start + 4);
                const pages = [];
                for (let page = start; page <= end; page += 1) {
                    pages.push(page);
                }
                return pages;
            },

            activeFilterCount() {
                let count = 0;
                if (this.filters.source) count += 1;
                if (this.filters.purity) count += 1;
                if (this.filters.search) count += 1;
                if (this.filters.min_discount !== DEFAULT_FILTERS.min_discount) count += 1;
                if (this.filters.max_discount !== DEFAULT_FILTERS.max_discount) count += 1;
                if (this.filters.min_weight !== DEFAULT_FILTERS.min_weight) count += 1;
                if (this.filters.max_weight !== DEFAULT_FILTERS.max_weight) count += 1;
                if (this.filters.onlyFavorites) count += 1;
                return count;
            },

            uniqueSources() {
                return [...new Set(this.allProducts.map((product) => product.source).filter(Boolean))].sort();
            },

            uniquePurities() {
                return [...new Set(this.allProducts.map((product) => product.purity).filter(Boolean))].sort();
            },

            isDesktop() {
                return this.windowWidth >= 1024;
            },

            scanLabel() {
                if (!this.selectedScanId) return 'No scan loaded';
                return this.selectedScanIsLatest ? 'Latest market capture' : 'Archived scan selected';
            },

            scanTimeFormatted() {
                if (!this.selectedScanTimestamp) return 'No timestamp';
                return this.formatDateTime(this.selectedScanTimestamp);
            },

            liveSpotPrice() {
                return numeric(this.spotPrice?.gold?.per_gram?.['999_landed']);
            },

            totalInventoryValue() {
                return this.allProducts.reduce((sum, product) => sum + numeric(product.selling_price), 0);
            },

            averageDiscount() {
                if (!this.allProducts.length) return 0;
                const total = this.allProducts.reduce((sum, product) => sum + numeric(product.discount_percent), 0);
                return total / this.allProducts.length;
            },

            averagePricePerGram() {
                if (!this.allProducts.length) return 0;
                const total = this.allProducts.reduce((sum, product) => sum + numeric(product.price_per_gram), 0);
                return total / this.allProducts.length;
            },

            goodDealsCount() {
                return this.allProducts.filter((product) => numeric(product.discount_percent) >= 10).length;
            },

            bestCurrentDeal() {
                if (!this.allProducts.length) return null;
                return [...this.allProducts].sort((a, b) => numeric(b.discount_percent) - numeric(a.discount_percent))[0];
            },

            favoriteProducts() {
                return this.allProducts.filter((product) => this.favorites.includes(product.url));
            },

            currentSourceDistribution() {
                const distribution = {};
                this.allProducts.forEach((product) => {
                    const source = product.source || 'Unknown';
                    distribution[source] = (distribution[source] || 0) + 1;
                });
                return distribution;
            },

            scanTrendSeries() {
                return [...this.scans].slice(0, 10).reverse();
            },

            historicalStats() {
                return this.summaryStats.historical || {};
            },

            latestProductsPreview() {
                return [...this.sortedProducts].slice(0, 4);
            },
        },

        watch: {
            filters: {
                handler() {
                    this.currentPage = 1;
                },
                deep: true,
            },
            sortBy() {
                this.currentPage = 1;
            },
            sortOrder() {
                this.currentPage = 1;
            },
            itemsPerPage() {
                this.currentPage = 1;
            },
            favorites: {
                handler(value) {
                    localStorage.setItem('goldFavorites', JSON.stringify(value));
                },
                deep: true,
            },
            darkMode(value) {
                localStorage.setItem('goldDarkMode', String(value));
                this.applyTheme();
                this.$nextTick(() => this.renderCharts());
            },
            activeTab() {
                this.$nextTick(() => this.renderCharts());
            },
            allProducts() {
                this.currentPage = 1;
                this.$nextTick(() => this.renderCharts());
            },
            scans() {
                this.$nextTick(() => this.renderCharts());
            },
            timeline() {
                this.$nextTick(() => this.renderCharts());
            },
        },

        mounted() {
            this.applyTheme();
            window.addEventListener('resize', this.handleResize);
            this.initKeyboardShortcuts();
            this.boot();
            this.setupAutoRefresh();
        },

        beforeDestroy() {
            window.removeEventListener('keydown', this.handleKeyDown);
            window.removeEventListener('resize', this.handleResize);
            this.destroyCharts();
        },

        methods: {
            async boot() {
                this.loading = true;
                this.bootError = '';
                try {
                    await this.refreshDashboardData({ preserveSelection: false });
                } catch (error) {
                    this.bootError = this.getErrorMessage(error, 'Unable to load the dashboard.');
                } finally {
                    this.loading = false;
                }
            },

            async refreshDashboardData({ preserveSelection = true, clearCache = false } = {}) {
                const selectedScanId = preserveSelection ? this.selectedScanId : null;
                const selectedScanIsLatest = preserveSelection ? this.selectedScanIsLatest : true;

                if (clearCache) {
                    await axios.post('/api/v1/cache/clear');
                }

                await Promise.all([
                    this.fetchScans(),
                    this.fetchSummaryStats(),
                    this.fetchSpotPrice(),
                    this.fetchTimeline(),
                ]);

                if (selectedScanId && !selectedScanIsLatest && this.scans.some((scan) => scan.scan_id === selectedScanId)) {
                    await this.loadScanDetails(selectedScanId, { keepTab: true, silent: true });
                } else {
                    await this.loadLatestScan({ silent: true });
                }
            },

            async fetchScans() {
                const response = await axios.get('/api/v1/historical/scans?limit=14');
                this.scans = safeArray(response.data);
                if (this.scans.length) {
                    this.latestScanId = this.scans[0].scan_id;
                    this.latestScanTimestamp = this.scans[0].timestamp;
                } else {
                    this.latestScanId = null;
                    this.latestScanTimestamp = null;
                }
            },

            async fetchSummaryStats() {
                const response = await axios.get('/api/v1/stats/summary');
                this.summaryStats = response.data || { live: {}, historical: {} };
            },

            async fetchSpotPrice() {
                const response = await axios.get('/api/v1/spot-price');
                this.spotPrice = response.data || null;
            },

            async fetchTimeline() {
                const response = await axios.get('/api/v1/historical/timeline?days=30');
                this.timeline = response.data || { timeline: {}, total_scans: 0, total_products: 0 };
            },

            async loadLatestScan({ silent = false } = {}) {
                if (!this.scans.length) {
                    this.allProducts = [];
                    this.selectedScanId = null;
                    this.selectedScanTimestamp = null;
                    this.selectedScanIsLatest = true;
                    this.latestScanId = null;
                    this.latestScanTimestamp = null;
                    return;
                }
                await this.loadScanDetails(this.scans[0].scan_id, { isLatest: true, silent });
            },

            async loadScanDetails(scanId, { isLatest = false, keepTab = false, silent = false } = {}) {
                this.loadingProducts = true;
                if (!silent) {
                    this.bootError = '';
                }
                try {
                    const response = await axios.get(`/api/v1/historical/scan/${scanId}`);
                    const scanData = response.data || {};
                    this.allProducts = safeArray(scanData.products);
                    this.selectedScanId = scanData.scan_id || scanId;
                    this.selectedScanTimestamp = scanData.timestamp || null;
                    this.selectedScanIsLatest = Boolean(isLatest || this.latestScanId === this.selectedScanId);
                    if (!keepTab) {
                        this.activeTab = 'products';
                    }
                    this.mobileMenuOpen = false;
                    this.showMobileFilters = false;
                    if (!silent) {
                        this.showNotification('info', this.selectedScanIsLatest ? 'Loaded latest scan.' : 'Loaded archived scan.');
                    }
                } catch (error) {
                    const message = this.getErrorMessage(error, 'Unable to load scan details.');
                    this.bootError = message;
                    this.showNotification('error', message);
                } finally {
                    this.loadingProducts = false;
                }
            },

            async returnToLatest() {
                await this.loadLatestScan();
            },

            async refreshData() {
                this.refreshing = true;
                this.bootError = '';
                try {
                    await this.refreshDashboardData({ preserveSelection: true, clearCache: true });
                    this.showNotification('success', 'Dashboard refreshed.');
                } catch (error) {
                    this.showNotification('error', this.getErrorMessage(error, 'Refresh failed.'));
                } finally {
                    this.refreshing = false;
                }
            },

            async startNewScan() {
                this.scanning = true;
                try {
                    const response = await axios.post('/api/v1/scan');
                    this.showScanModal = false;
                    this.showNotification('success', response.data?.message || 'Scan completed.');
                    await this.refreshDashboardData({ preserveSelection: false, clearCache: true });
                    await this.loadLatestScan({ silent: true });
                } catch (error) {
                    this.showNotification('error', this.getErrorMessage(error, 'Scan failed.'));
                } finally {
                    this.scanning = false;
                }
            },

            async checkForNewScan() {
                try {
                    const response = await axios.get('/api/v1/historical/scans?limit=1');
                    const latest = safeArray(response.data)[0];
                    if (latest && latest.scan_id !== this.latestScanId) {
                        this.showNotification('info', 'New scan detected. Refreshing archive.');
                        await this.refreshDashboardData({ preserveSelection: true, clearCache: false });
                    }
                } catch (error) {
                    console.error('Scan polling failed', error);
                }
            },

            handleResize() {
                this.windowWidth = window.innerWidth;
                if (this.isDesktop) {
                    this.showMobileFilters = false;
                    this.mobileMenuOpen = false;
                }
            },

            exportData() {
                const rows = this.sortedProducts;
                const fileBase = this.selectedScanId ? `gold-deals-${this.selectedScanId}` : 'gold-deals';
                if (this.exportFormat === 'json') {
                    this.downloadBlob(JSON.stringify(rows, null, 2), `${fileBase}.json`, 'application/json');
                } else {
                    const headers = ['Source', 'Brand', 'Title', 'Purity', 'Weight (g)', 'Price', 'Expected', 'Discount %', 'Price/g', 'URL'];
                    const csvRows = rows.map((product) => [
                        product.source,
                        product.brand,
                        String(product.title || '').replace(/,/g, ';'),
                        product.purity,
                        numeric(product.weight_grams),
                        numeric(product.selling_price),
                        numeric(product.expected_price),
                        numeric(product.discount_percent),
                        numeric(product.price_per_gram),
                        product.url,
                    ]);
                    const csv = [headers, ...csvRows].map((row) => row.join(',')).join('\n');
                    this.downloadBlob(csv, `${fileBase}.csv`, 'text/csv;charset=utf-8');
                }
                this.showExportModal = false;
                this.showNotification('success', 'Export ready.');
            },

            downloadBlob(content, filename, mimeType) {
                const blob = new Blob([content], { type: mimeType });
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = filename;
                link.click();
                URL.revokeObjectURL(url);
            },

            resetFilters() {
                this.filters = cloneFilters();
                this.showNotification('info', 'Filters reset.');
            },

            toggleFavorite(product) {
                const index = this.favorites.indexOf(product.url);
                if (index === -1) {
                    this.favorites.push(product.url);
                    this.showNotification('success', 'Saved to shortlist.');
                } else {
                    this.favorites.splice(index, 1);
                    this.showNotification('info', 'Removed from shortlist.');
                }
            },

            isFavorite(product) {
                return this.favorites.includes(product.url);
            },

            viewProductDetails(product) {
                this.selectedProduct = product;
            },

            closeAllPanels() {
                this.mobileMenuOpen = false;
                this.showMobileFilters = false;
                this.showShortcuts = false;
                this.showScanModal = false;
                this.showExportModal = false;
                this.showFavoritesModal = false;
                this.selectedProduct = null;
            },

            shareProduct(product) {
                const shareData = {
                    title: product.title,
                    text: `${product.brand || product.source} · ${this.formatPercent(product.discount_percent)} · ${this.formatCurrency(product.selling_price)}`,
                    url: product.url,
                };
                if (navigator.share) {
                    navigator.share(shareData).catch(() => {});
                    return;
                }
                navigator.clipboard.writeText(product.url);
                this.showNotification('success', 'Product link copied.');
            },

            copyToClipboard(text, successMessage = 'Copied.') {
                if (!text) return;
                navigator.clipboard.writeText(text);
                this.showNotification('success', successMessage);
            },

            handleImageError(event) {
                event.target.src = 'https://placehold.co/640x640/f1e7cf/4f3a14?text=Gold+Deal';
            },

            focusSearch() {
                const element = document.getElementById('search-input');
                if (element) {
                    element.focus();
                    element.select();
                }
            },

            goToPage(page) {
                if (page < 1 || page > this.totalPages) return;
                this.currentPage = page;
            },

            nextPage() {
                this.goToPage(this.currentPage + 1);
            },

            prevPage() {
                this.goToPage(this.currentPage - 1);
            },

            formatCurrency(value) {
                return `₹${numeric(value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
            },

            formatWeight(value) {
                const amount = numeric(value);
                if (amount >= 1000) {
                    return `${(amount / 1000).toFixed(2)} kg`;
                }
                return `${amount} g`;
            },

            formatPercent(value) {
                const amount = numeric(value);
                return `${amount.toFixed(1)}%`;
            },

            formatDateTime(value) {
                if (!value) return 'Unknown time';
                return new Date(value).toLocaleString('en-IN', {
                    day: '2-digit',
                    month: 'short',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                });
            },

            formatDate(value) {
                if (!value) return 'Unknown';
                return new Date(value).toLocaleDateString('en-IN', {
                    day: '2-digit',
                    month: 'short',
                    year: 'numeric',
                });
            },

            formatTimeAgo(value) {
                if (!value) return 'Unknown';
                const diffMs = Date.now() - new Date(value).getTime();
                const diffHours = Math.round(diffMs / (1000 * 60 * 60));
                if (diffHours < 1) return 'Less than 1 hour ago';
                if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
                const diffDays = Math.round(diffHours / 24);
                return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
            },

            discountTone(value) {
                return numeric(value) >= 0 ? 'tone-positive' : 'tone-negative';
            },

            getErrorMessage(error, fallback) {
                return (
                    error?.response?.data?.detail?.message ||
                    error?.response?.data?.detail ||
                    error?.message ||
                    fallback
                );
            },

            showNotification(type, message, duration = 3200) {
                const id = this.notificationId + 1;
                this.notificationId = id;
                this.notifications.push({ id, type, message });
                window.setTimeout(() => {
                    this.notifications = this.notifications.filter((notification) => notification.id !== id);
                }, duration);
            },

            notificationClass(type) {
                if (type === 'error') return 'toast toast-error';
                if (type === 'success') return 'toast toast-success';
                return 'toast toast-info';
            },

            setupAutoRefresh() {
                window.setInterval(() => this.fetchSpotPrice().catch(() => {}), 5 * 60 * 1000);
                window.setInterval(() => this.checkForNewScan(), 5 * 60 * 1000);
            },

            applyTheme() {
                document.documentElement.classList.toggle('dark', this.darkMode);
            },

            toggleTheme() {
                this.darkMode = !this.darkMode;
            },

            initKeyboardShortcuts() {
                window.addEventListener('keydown', this.handleKeyDown);
            },

            handleKeyDown(event) {
                if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'f') {
                    event.preventDefault();
                    this.focusSearch();
                }
                if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'r') {
                    event.preventDefault();
                    this.refreshData();
                }
                if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'n') {
                    event.preventDefault();
                    this.showScanModal = true;
                }
                if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'd') {
                    event.preventDefault();
                    this.toggleTheme();
                }
                if (event.key === 'Escape') {
                    this.closeAllPanels();
                }
            },

            destroyCharts() {
                if (this.distributionChart) {
                    this.distributionChart.destroy();
                    this.distributionChart = null;
                }
                if (this.scanTrendChart) {
                    this.scanTrendChart.destroy();
                    this.scanTrendChart = null;
                }
            },

            renderCharts() {
                if (typeof Chart === 'undefined') return;
                this.renderDistributionChart();
                this.renderScanTrendChart();
            },

            renderDistributionChart() {
                const canvas = document.getElementById('distributionChart');
                if (!canvas) return;
                if (this.distributionChart) {
                    this.distributionChart.destroy();
                }
                const labels = Object.keys(this.currentSourceDistribution);
                const data = Object.values(this.currentSourceDistribution);
                if (!labels.length) return;
                this.distributionChart = new Chart(canvas.getContext('2d'), {
                    type: 'doughnut',
                    data: {
                        labels,
                        datasets: [{
                            data,
                            backgroundColor: ['#d6a648', '#8f6a20', '#3d6a80', '#7a3f29', '#5b7f58'],
                            borderWidth: 0,
                        }],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                labels: {
                                    color: this.darkMode ? '#f8f3e7' : '#3d3122',
                                },
                            },
                        },
                    },
                });
            },

            renderScanTrendChart() {
                const canvas = document.getElementById('scanTrendChart');
                if (!canvas) return;
                if (this.scanTrendChart) {
                    this.scanTrendChart.destroy();
                }
                if (!this.scanTrendSeries.length) return;
                this.scanTrendChart = new Chart(canvas.getContext('2d'), {
                    type: 'line',
                    data: {
                        labels: this.scanTrendSeries.map((scan) => this.formatDate(scan.timestamp)),
                        datasets: [
                            {
                                label: 'Products',
                                data: this.scanTrendSeries.map((scan) => numeric(scan.total_products)),
                                borderColor: '#d6a648',
                                backgroundColor: 'rgba(214, 166, 72, 0.18)',
                                fill: true,
                                tension: 0.35,
                            },
                            {
                                label: 'Good deals',
                                data: this.scanTrendSeries.map((scan) => numeric(scan.good_deals)),
                                borderColor: '#3d6a80',
                                backgroundColor: 'rgba(61, 106, 128, 0.12)',
                                fill: true,
                                tension: 0.35,
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                labels: {
                                    color: this.darkMode ? '#f8f3e7' : '#3d3122',
                                },
                            },
                        },
                        scales: {
                            x: {
                                ticks: { color: this.darkMode ? '#d9d1c2' : '#6f5d46' },
                                grid: { color: this.darkMode ? 'rgba(255,255,255,0.08)' : 'rgba(61,49,34,0.06)' },
                            },
                            y: {
                                ticks: { color: this.darkMode ? '#d9d1c2' : '#6f5d46' },
                                grid: { color: this.darkMode ? 'rgba(255,255,255,0.08)' : 'rgba(61,49,34,0.06)' },
                            },
                        },
                    },
                });
            },
        },
    });
})();
