(function () {
    const searchInput = document.getElementById("globalMedicineSearch");
    const searchResults = document.getElementById("globalSearchResults");
    let searchTimer = null;

    if (searchInput && searchResults) {
        const renderResults = (items) => {
            if (!items.length) {
                searchResults.innerHTML = '<div class="search-empty">No medicines found</div>';
                searchResults.classList.add("show");
                return;
            }

            searchResults.innerHTML = items.map((item) => `
                <a href="${item.url}" class="search-result-item">
                    <strong>${item.name}</strong>
                    <span>${item.generic || "No generic name"} - ${item.barcode || "No barcode"}</span>
                </a>
            `).join("");
            searchResults.classList.add("show");
        };

        searchInput.addEventListener("input", () => {
            clearTimeout(searchTimer);
            const query = searchInput.value.trim();
            if (query.length < 2) {
                searchResults.classList.remove("show");
                searchResults.innerHTML = "";
                return;
            }

            searchTimer = setTimeout(async () => {
                const url = `${searchInput.dataset.searchUrl}?q=${encodeURIComponent(query)}`;
                const response = await fetch(url, { headers: { "Accept": "application/json" } });
                renderResults(await response.json());
            }, 220);
        });

        document.addEventListener("click", (event) => {
            if (!searchInput.contains(event.target) && !searchResults.contains(event.target)) {
                searchResults.classList.remove("show");
            }
        });
    }

    if (window.jQuery && window.DataTable) {
        document.querySelectorAll(".data-table").forEach((table) => {
            if (!table.dataset.dtReady) {
                new DataTable(table, {
                    responsive: true,
                    pageLength: 10,
                    order: [],
                    language: {
                        search: "Filter:",
                        emptyTable: "No records found"
                    }
                });
                table.dataset.dtReady = "1";
            }
        });
    }

    const purchaseLines = document.getElementById("purchaseLines");
    const addPurchaseRow = document.getElementById("addPurchaseRow");
    const purchaseTotal = document.getElementById("purchaseTotal");

    const money = (value) => `Rs ${Number(value || 0).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    })}`;

    const updatePurchaseTotals = () => {
        if (!purchaseLines || !purchaseTotal) {
            return;
        }

        let total = 0;
        purchaseLines.querySelectorAll(".purchase-line").forEach((row) => {
            const quantity = Number(row.querySelector(".line-qty")?.value || 0);
            const price = Number(row.querySelector(".line-purchase")?.value || 0);
            const subtotal = quantity * price;
            total += subtotal;
            const subtotalCell = row.querySelector(".line-subtotal");
            if (subtotalCell) {
                subtotalCell.textContent = money(subtotal);
            }
        });
        purchaseTotal.textContent = money(total);
    };

    if (purchaseLines) {
        purchaseLines.addEventListener("input", updatePurchaseTotals);
        purchaseLines.addEventListener("click", (event) => {
            const button = event.target.closest(".remove-line");
            if (!button) {
                return;
            }

            if (purchaseLines.querySelectorAll(".purchase-line").length > 1) {
                button.closest(".purchase-line").remove();
                updatePurchaseTotals();
            }
        });
        updatePurchaseTotals();
    }

    if (addPurchaseRow && purchaseLines) {
        addPurchaseRow.addEventListener("click", () => {
            const source = purchaseLines.querySelector(".purchase-line");
            if (!source) {
                return;
            }

            const clone = source.cloneNode(true);
            clone.querySelectorAll("input").forEach((input) => {
                input.value = "";
            });
            clone.querySelectorAll("select").forEach((select) => {
                select.selectedIndex = 0;
            });
            const subtotal = clone.querySelector(".line-subtotal");
            if (subtotal) {
                subtotal.textContent = "Rs 0.00";
            }
            purchaseLines.appendChild(clone);
            updatePurchaseTotals();
        });
    }

    const saleLines = document.getElementById("saleLines");
    const addSaleRow = document.getElementById("addSaleRow");
    const saleTotal = document.getElementById("saleTotal");

    const updateSaleRow = (row, fillPrice) => {
        const selected = row.querySelector(".sale-medicine-select")?.selectedOptions[0];
        const stockCell = row.querySelector(".sale-stock");
        const priceInput = row.querySelector(".sale-price");
        const quantityInput = row.querySelector(".sale-qty");
        const subtotalCell = row.querySelector(".sale-subtotal");

        if (stockCell) {
            stockCell.textContent = selected?.dataset.stock || "0";
        }

        if (fillPrice && priceInput && selected?.dataset.price) {
            priceInput.value = Number(selected.dataset.price || 0).toFixed(2);
        }

        const quantity = Number(quantityInput?.value || 0);
        const price = Number(priceInput?.value || 0);
        if (subtotalCell) {
            subtotalCell.textContent = money(quantity * price);
        }
    };

    const updateSaleTotals = (fillPrice) => {
        if (!saleLines || !saleTotal) {
            return;
        }

        let total = 0;
        saleLines.querySelectorAll(".sale-line").forEach((row) => {
            updateSaleRow(row, fillPrice);
            const quantity = Number(row.querySelector(".sale-qty")?.value || 0);
            const price = Number(row.querySelector(".sale-price")?.value || 0);
            total += quantity * price;
        });
        saleTotal.textContent = money(total);
    };

    if (saleLines) {
        saleLines.addEventListener("change", (event) => {
            updateSaleTotals(event.target.classList.contains("sale-medicine-select"));
        });
        saleLines.addEventListener("input", () => updateSaleTotals(false));
        saleLines.addEventListener("click", (event) => {
            const button = event.target.closest(".remove-sale-line");
            if (!button) {
                return;
            }

            if (saleLines.querySelectorAll(".sale-line").length > 1) {
                button.closest(".sale-line").remove();
                updateSaleTotals(false);
            }
        });
        updateSaleTotals(false);
    }

    if (addSaleRow && saleLines) {
        addSaleRow.addEventListener("click", () => {
            const source = saleLines.querySelector(".sale-line");
            if (!source) {
                return;
            }

            const clone = source.cloneNode(true);
            clone.querySelectorAll("input").forEach((input) => {
                input.value = "";
            });
            clone.querySelectorAll("select").forEach((select) => {
                select.selectedIndex = 0;
            });
            const stock = clone.querySelector(".sale-stock");
            if (stock) {
                stock.textContent = "0";
            }
            const subtotal = clone.querySelector(".sale-subtotal");
            if (subtotal) {
                subtotal.textContent = "Rs 0.00";
            }
            saleLines.appendChild(clone);
            updateSaleTotals(false);
        });
    }

    const posSearch = document.getElementById("posSearch");
    const posSearchResults = document.getElementById("posSearchResults");
    const posCartRows = document.getElementById("posCartRows");
    const posHiddenItems = document.getElementById("posHiddenItems");
    const posCartTotal = document.getElementById("posCartTotal");
    const posRunningTotal = document.getElementById("posRunningTotal");
    const posGrandTotal = document.getElementById("posGrandTotal");
    const posChange = document.getElementById("posChange");
    const posCartCount = document.getElementById("posCartCount");
    const posDiscount = document.getElementById("discount");
    const posCash = document.getElementById("cash_received");
    const posCart = new Map();
    let posTimer = null;

    const renderPosCart = () => {
        if (!posCartRows || !posHiddenItems) {
            return;
        }

        const items = Array.from(posCart.values());
        if (!items.length) {
            posCartRows.innerHTML = '<tr><td colspan="5" class="empty-state">No medicines added.</td></tr>';
            posHiddenItems.innerHTML = "";
        } else {
            posCartRows.innerHTML = items.map((item) => {
                const subtotal = item.quantity * item.price;
                return `
                    <tr>
                        <td>${item.name}<small class="d-block text-muted">${item.generic || ""} - Batch ${item.batch}</small></td>
                        <td>
                            <div class="btn-group btn-group-sm" role="group">
                                <button type="button" class="btn btn-outline-primary pos-qty" data-id="${item.id}" data-step="-1"><i class="bi bi-dash"></i></button>
                                <span class="btn btn-light">${item.quantity}</span>
                                <button type="button" class="btn btn-outline-primary pos-qty" data-id="${item.id}" data-step="1"><i class="bi bi-plus"></i></button>
                            </div>
                            <small class="d-block text-muted">Stock ${item.stock}</small>
                        </td>
                        <td>Rs ${item.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                        <td class="text-end">${money(subtotal)}</td>
                        <td class="text-end"><button type="button" class="btn btn-sm icon-btn table-icon danger pos-remove" data-id="${item.id}"><i class="bi bi-x-lg"></i></button></td>
                    </tr>
                `;
            }).join("");
            posHiddenItems.innerHTML = items.map((item) => `
                <input type="hidden" name="medicine_id[]" value="${item.medicineId}">
                <input type="hidden" name="quantity[]" value="${item.quantity}">
                <input type="hidden" name="unit_price[]" value="${item.price}">
            `).join("");
        }

        const total = items.reduce((sum, item) => sum + item.quantity * item.price, 0);
        const discount = Number(posDiscount?.value || 0);
        const cash = Number(posCash?.value || 0);
        const grand = Math.max(total - discount, 0);
        if (posCartTotal) {
            posCartTotal.textContent = money(total);
        }
        if (posRunningTotal) {
            posRunningTotal.textContent = money(total);
        }
        if (posGrandTotal) {
            posGrandTotal.textContent = money(grand);
        }
        if (posChange) {
            posChange.textContent = money(Math.max(cash - grand, 0));
        }
        if (posCartCount) {
            posCartCount.textContent = String(items.reduce((sum, item) => sum + item.quantity, 0));
        }
    };

    if (posSearch && posSearchResults) {
        posSearch.addEventListener("input", () => {
            clearTimeout(posTimer);
            const query = posSearch.value.trim();
            if (query.length < 2) {
                posSearchResults.innerHTML = '<tr><td colspan="5" class="empty-state">Search to add medicines into cart.</td></tr>';
                return;
            }

            posTimer = setTimeout(async () => {
                const response = await fetch(`${posSearch.dataset.searchUrl}?q=${encodeURIComponent(query)}`, { headers: { "Accept": "application/json" } });
                const items = await response.json();
                if (!items.length) {
                    posSearchResults.innerHTML = '<tr><td colspan="5" class="empty-state">No available stock found.</td></tr>';
                    return;
                }
                posSearchResults.innerHTML = items.map((item) => `
                    <tr>
                        <td>${item.medicine_name}<small class="d-block text-muted">${item.generic_name || ""} - ${item.barcode || ""}</small></td>
                        <td>${item.available_stock}</td>
                        <td>${money(item.sale_price)}</td>
                        <td>${item.batch_no}<small class="d-block text-muted">Exp ${item.expiry_date}</small></td>
                        <td class="text-end">
                            <button type="button" class="btn btn-sm btn-primary pos-add"
                                data-id="${item.medicine_id}-${item.batch_no}"
                                data-medicine-id="${item.medicine_id}"
                                data-name="${item.medicine_name}"
                                data-generic="${item.generic_name || ""}"
                                data-batch="${item.batch_no}"
                                data-stock="${item.available_stock}"
                                data-price="${item.sale_price}">
                                <i class="bi bi-plus-circle me-1"></i>Add
                            </button>
                        </td>
                    </tr>
                `).join("");
            }, 180);
        });

        posSearchResults.addEventListener("click", (event) => {
            const button = event.target.closest(".pos-add");
            if (!button) {
                return;
            }
            const id = button.dataset.id;
            const existing = posCart.get(id);
            const stock = Number(button.dataset.stock || 0);
            if (existing) {
                existing.quantity = Math.min(existing.quantity + 1, stock);
            } else {
                posCart.set(id, {
                    id,
                    medicineId: button.dataset.medicineId,
                    name: button.dataset.name,
                    generic: button.dataset.generic,
                    batch: button.dataset.batch,
                    stock,
                    price: Number(button.dataset.price || 0),
                    quantity: 1
                });
            }
            renderPosCart();
        });
    }

    if (posCartRows) {
        posCartRows.addEventListener("click", (event) => {
            const qtyButton = event.target.closest(".pos-qty");
            if (qtyButton) {
                const item = posCart.get(qtyButton.dataset.id);
                if (item) {
                    item.quantity += Number(qtyButton.dataset.step || 0);
                    if (item.quantity <= 0) {
                        posCart.delete(item.id);
                    } else {
                        item.quantity = Math.min(item.quantity, item.stock);
                    }
                    renderPosCart();
                }
                return;
            }

            const removeButton = event.target.closest(".pos-remove");
            if (removeButton) {
                posCart.delete(removeButton.dataset.id);
                renderPosCart();
            }
        });
    }

    if (posDiscount || posCash) {
        [posDiscount, posCash].forEach((input) => {
            input?.addEventListener("input", renderPosCart);
        });
        renderPosCart();
    }

    const dataElement = document.getElementById("dashboard-data");
    if (!window.Chart) {
        return;
    }

    const palette = {
        teal: "#0f766e",
        blue: "#2563eb",
        green: "#16a34a",
        amber: "#d97706",
        red: "#dc2626",
        cyan: "#0891b2",
        violet: "#7c3aed",
        slate: "#475569"
    };

    const withFallback = (dataset, label) => {
        if (dataset && Array.isArray(dataset.labels) && dataset.labels.length) {
            return dataset;
        }

        return {
            labels: ["No data"],
            values: [0],
            empty: true,
            label
        };
    };

    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                labels: {
                    boxWidth: 12,
                    usePointStyle: true
                }
            },
            tooltip: {
                backgroundColor: "#172033",
                padding: 12,
                cornerRadius: 8
            }
        }
    };

    if (dataElement) {
        const dashboardData = JSON.parse(dataElement.textContent || "{}");
        const dailySales = withFallback(dashboardData.dailySales, "Daily sales");
        const monthlyRevenue = withFallback(dashboardData.monthlyRevenue, "Monthly revenue");
        const categories = withFallback(dashboardData.categories, "Categories");

        const dailyCanvas = document.getElementById("dailySalesChart");
        if (dailyCanvas) {
            new Chart(dailyCanvas, {
                type: "line",
                data: {
                    labels: dailySales.labels,
                    datasets: [{
                        label: "Revenue",
                        data: dailySales.values,
                        borderColor: palette.teal,
                        backgroundColor: "rgba(15, 118, 110, 0.12)",
                        fill: true,
                        tension: 0.38,
                        pointRadius: 3,
                        pointHoverRadius: 5
                    }]
                },
                options: {
                    ...commonOptions,
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: "rgba(148, 163, 184, 0.18)" }
                        },
                        x: {
                            grid: { display: false }
                        }
                    }
                }
            });
        }

        const monthlyCanvas = document.getElementById("monthlyRevenueChart");
        if (monthlyCanvas) {
            new Chart(monthlyCanvas, {
                type: "bar",
                data: {
                    labels: monthlyRevenue.labels,
                    datasets: [{
                        label: "Revenue",
                        data: monthlyRevenue.values,
                        backgroundColor: palette.blue,
                        borderRadius: 8,
                        maxBarThickness: 44
                    }]
                },
                options: {
                    ...commonOptions,
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: "rgba(148, 163, 184, 0.18)" }
                        },
                        x: {
                            grid: { display: false }
                        }
                    }
                }
            });
        }

        const categoryCanvas = document.getElementById("categoryChart");
        if (categoryCanvas) {
            new Chart(categoryCanvas, {
                type: "doughnut",
                data: {
                    labels: categories.labels,
                    datasets: [{
                        data: categories.values,
                        backgroundColor: [
                            palette.teal,
                            palette.blue,
                            palette.green,
                            palette.amber,
                            palette.cyan,
                            palette.violet,
                            palette.red,
                            palette.slate
                        ],
                        borderWidth: 0,
                        hoverOffset: 8
                    }]
                },
                options: {
                    ...commonOptions,
                    cutout: "68%",
                    plugins: {
                        ...commonOptions.plugins,
                        legend: {
                            position: "bottom",
                            labels: {
                                boxWidth: 10,
                                usePointStyle: true
                            }
                        }
                    }
                }
            });
        }
    }

    const reportsElement = document.getElementById("reports-data");
    if (!reportsElement) {
        return;
    }

    const reportsData = JSON.parse(reportsElement.textContent || "{}");
    const reportDailySales = withFallback(reportsData.reportDailySales, "Daily sales");
    const reportMonthlyRevenue = withFallback(reportsData.reportMonthlyRevenue, "Monthly revenue");
    const reportTopSelling = withFallback(reportsData.reportTopSelling, "Top selling");
    const reportInventoryHealth = withFallback(reportsData.reportInventoryHealth, "Inventory health");

    const reportDailyCanvas = document.getElementById("reportDailySalesChart");
    if (reportDailyCanvas) {
        new Chart(reportDailyCanvas, {
            type: "line",
            data: {
                labels: reportDailySales.labels,
                datasets: [{
                    label: "Revenue",
                    data: reportDailySales.values,
                    borderColor: palette.teal,
                    backgroundColor: "rgba(15, 118, 110, 0.12)",
                    fill: true,
                    tension: 0.38,
                    pointRadius: 3,
                    pointHoverRadius: 5
                }]
            },
            options: commonOptions
        });
    }

    const reportMonthlyCanvas = document.getElementById("reportMonthlyRevenueChart");
    if (reportMonthlyCanvas) {
        new Chart(reportMonthlyCanvas, {
            type: "bar",
            data: {
                labels: reportMonthlyRevenue.labels,
                datasets: [{
                    label: "Revenue",
                    data: reportMonthlyRevenue.values,
                    backgroundColor: palette.blue,
                    borderRadius: 8,
                    maxBarThickness: 44
                }]
            },
            options: commonOptions
        });
    }

    const reportTopCanvas = document.getElementById("reportTopSellingChart");
    if (reportTopCanvas) {
        new Chart(reportTopCanvas, {
            type: "bar",
            data: {
                labels: reportTopSelling.labels,
                datasets: [{
                    label: "Quantity sold",
                    data: reportTopSelling.values,
                    backgroundColor: palette.green,
                    borderRadius: 8,
                    maxBarThickness: 44
                }]
            },
            options: commonOptions
        });
    }

    const reportHealthCanvas = document.getElementById("reportInventoryHealthChart");
    if (reportHealthCanvas) {
        new Chart(reportHealthCanvas, {
            type: "doughnut",
            data: {
                labels: reportInventoryHealth.labels,
                datasets: [{
                    data: reportInventoryHealth.values,
                    backgroundColor: [palette.green, palette.amber, palette.red, palette.slate],
                    borderWidth: 0,
                    hoverOffset: 8
                }]
            },
            options: {
                ...commonOptions,
                cutout: "68%",
                plugins: {
                    ...commonOptions.plugins,
                    legend: {
                        position: "bottom",
                        labels: { boxWidth: 10, usePointStyle: true }
                    }
                }
            }
        });
    }
})();
