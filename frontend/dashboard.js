document.addEventListener("DOMContentLoaded", () => {

    const $ = (id) => document.getElementById(id);

    let products = [];
    let plans = [];
    let subscriptions = [];
    let invoices = [];

    // --------------------------
    // API HELPER
    // --------------------------

    async function api(url, options = {}) {
        const response = await fetch(url, {
            ...options,
            credentials: "same-origin",
            headers: {
                ...(options.body ? {
                    "Content-Type": "application/json"
                } : {}),
                ...(options.headers || {})
            }
        });

        if (response.status === 401) {
            window.location.href = "/";
            throw new Error("Your session expired. Please log in again.");
        }

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(
                typeof data.detail === "string"
                    ? data.detail
                    : "The request could not be completed."
            );
        }

        return data;
    }

    // --------------------------
    // MESSAGE
    // --------------------------

    function message(text, type = "success") {
        const box = $("alertMessage");

        box.textContent = text;
        box.className = `alert-message visible ${type}`;

        window.scrollTo({ top: 0, behavior: "smooth" });

        setTimeout(() => {
            box.className = "alert-message";
        }, 5000);
    }

    function escapeHTML(value) {
        return String(value ?? "").replace(/[&<>"']/g, char => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        })[char]);
    }

    function money(amount, currency = "USD") {
        const value = Number(amount || 0) / 100;

        try {
            return new Intl.NumberFormat("en-IN", {
                style: "currency",
                currency: currency
            }).format(value);
        } catch {
            return `${currency} ${value.toFixed(2)}`;
        }
    }

    function statusBadge(status) {
        return `<span class="status ${escapeHTML(status)}">${escapeHTML(status)}</span>`;
    }

    function emptyRow(columns, text) {
        return `<tr><td colspan="${columns}" class="empty-cell">${escapeHTML(text)}</td></tr>`;
    }

    // --------------------------
    // SECTION NAVIGATION
    // --------------------------

    function showSection(section) {
        document.querySelectorAll(".page-section").forEach(item => {
            item.classList.remove("active");
        });

        document.querySelectorAll(".nav-item[data-section]").forEach(item => {
            item.classList.toggle(
                "active",
                item.dataset.section === section
            );
        });

        const selected = $(`section-${section}`);

        if (!selected) return;

        selected.classList.add("active");

        const navButton = document.querySelector(
            `.nav-item[data-section="${section}"]`
        );

        $("breadcrumbTitle").textContent =
            navButton ? navButton.textContent.trim() : "Overview";

        $("sidebar").classList.remove("open");

        if (section === "overview") loadOverview();
        if (section === "products") loadProducts();
        if (section === "plans") loadPlans();
        if (section === "subscriptions") loadSubscriptions();
        if (section === "invoices") loadInvoices();
    }

    document.querySelectorAll(".nav-item[data-section]").forEach(button => {
        button.addEventListener("click", () => {
            showSection(button.dataset.section);
        });
    });

    document.querySelectorAll("[data-go]").forEach(button => {
        button.addEventListener("click", () => {
            showSection(button.dataset.go);
        });
    });

    $("menuToggle").addEventListener("click", () => {
        $("sidebar").classList.toggle("open");
    });


    // --------------------------
    // CURRENT USER
    // --------------------------

    async function loadCurrentUser() {
        const data = await api("/auth/me");
        const user = data.user;

        $("userEmail").textContent = user.email;
        $("userAvatar").textContent =
            user.email.charAt(0).toUpperCase();

        $("accountEmail").textContent = user.email;
        $("accountRole").textContent = `Role: ${user.role}`;

        $("accountAvatar").textContent =
            user.email.charAt(0).toUpperCase();
    }


    // --------------------------
    // PRODUCTS
    // --------------------------

    async function loadProducts() {
        try {
            products = await api("/products");

            $("productCount").textContent = products.length;

            $("productsTable").innerHTML = products.length
                ? products.map(product => `
                    <tr>
                        <td><strong>${escapeHTML(product.name)}</strong></td>
                        <td>${escapeHTML(product.type)}</td>
                        <td>${money(product.sales_price_minor_units)}</td>
                        <td><span class="status ACTIVE">Active</span></td>
                    </tr>
                `).join("")
                : emptyRow(4, "No products available.");

            updateProductOptions();

        } catch (error) {
            message(error.message, "error");
        }
    }

    function updateProductOptions() {
        $("subscriptionProduct").innerHTML =
            `<option value="">Select a product</option>` +
            products.map(product => `
                <option value="${product.id}">
                    ${escapeHTML(product.name)}
                </option>
            `).join("");
    }

    $("showProductForm").addEventListener("click", () => {
        $("productFormCard").classList.toggle("hidden");
    });

    $("cancelProductForm").addEventListener("click", () => {
        $("productFormCard").classList.add("hidden");
        $("productForm").reset();
    });

    $("productForm").addEventListener("submit", async event => {
        event.preventDefault();

        const form = new FormData(event.target);

        const payload = {
            name: form.get("name").trim(),
            type: form.get("type"),
            sales_price_minor_units: Number(form.get("sales_price_minor_units")),
            cost_price_minor_units: Number(form.get("cost_price_minor_units")),
            notes: form.get("notes") || null
        };

        try {
            await api("/products", {
                method: "POST",
                body: JSON.stringify(payload)
            });

            event.target.reset();
            $("productFormCard").classList.add("hidden");

            message("Product created successfully.");
            await loadProducts();

        } catch (error) {
            message(error.message, "error");
        }
    });


    // --------------------------
    // SUBSCRIPTION PLANS
    // --------------------------

    async function loadPlans() {
        try {
            plans = await api("/plans");

            $("planCount").textContent = plans.length;

            $("plansTable").innerHTML = plans.length
                ? plans.map(plan => `
                    <tr>
                        <td><strong>${escapeHTML(plan.name)}</strong></td>
                        <td>${escapeHTML(plan.billing_frequency)}</td>
                        <td>${money(plan.base_cost_minor_units, plan.currency)}</td>
                        <td>${escapeHTML(plan.currency)}</td>
                        <td>${escapeHTML(plan.available_from)}</td>
                    </tr>
                `).join("")
                : emptyRow(5, "No subscription plans available.");

            $("subscriptionPlan").innerHTML =
                `<option value="">Select a plan</option>` +
                plans.map(plan => `
                    <option value="${plan.id}">
                        ${escapeHTML(plan.name)} (${escapeHTML(plan.billing_frequency)})
                    </option>
                `).join("");

        } catch (error) {
            message(error.message, "error");
        }
    }

    $("showPlanForm").addEventListener("click", () => {
        $("planFormCard").classList.toggle("hidden");
    });

    $("cancelPlanForm").addEventListener("click", () => {
        $("planFormCard").classList.add("hidden");
        $("planForm").reset();
    });

    $("planForm").addEventListener("submit", async event => {
        event.preventDefault();

        const form = new FormData(event.target);

        const payload = {
            name: form.get("name").trim(),
            billing_frequency: form.get("billing_frequency"),
            base_cost_minor_units: Number(form.get("base_cost_minor_units")),
            minimum_quantity: Number(form.get("minimum_quantity")),
            available_from: form.get("available_from"),
            available_until: form.get("available_until") || null,
            currency: form.get("currency").trim().toUpperCase()
        };

        try {
            await api("/plans", {
                method: "POST",
                body: JSON.stringify(payload)
            });

            event.target.reset();
            $("planFormCard").classList.add("hidden");

            message("Subscription plan created successfully.");
            await loadPlans();

        } catch (error) {
            message(error.message, "error");
        }
    });


    // --------------------------
    // SUBSCRIPTIONS
    // --------------------------

    async function loadSubscriptions() {
        try {
            subscriptions = await api("/subscriptions");

            $("subscriptionCount").textContent = subscriptions.length;

            $("subscriptionsTable").innerHTML = subscriptions.length
                ? subscriptions.map(sub => `
                    <tr>
                        <td><strong>${escapeHTML(sub.subscription_number)}</strong></td>
                        <td>${escapeHTML(sub.plan_id)}</td>
                        <td>${escapeHTML(sub.start_date)}</td>
                        <td>${escapeHTML(sub.expiry_date || "—")}</td>
                        <td>${statusBadge(sub.status)}</td>
                        <td>
                            ${sub.status === "DRAFT"
                                ? `<button class="action-button"
                                    data-confirm-sub="${sub.id}">
                                    Confirm
                                   </button>`
                                : "—"}
                        </td>
                    </tr>
                `).join("")
                : emptyRow(6, "No subscriptions found.");

            $("recentSubscriptions").innerHTML = subscriptions.length
                ? subscriptions.slice(0, 5).map(sub => `
                    <tr>
                        <td>${escapeHTML(sub.subscription_number)}</td>
                        <td>${escapeHTML(sub.plan_id)}</td>
                        <td>${escapeHTML(sub.start_date)}</td>
                        <td>${statusBadge(sub.status)}</td>
                    </tr>
                `).join("")
                : emptyRow(4, "No recent subscriptions.");

            updateSubscriptionOptions();

        } catch (error) {
            message(error.message, "error");
        }
    }

    function updateSubscriptionOptions() {
        const options = subscriptions
            .filter(sub => ["CONFIRMED", "ACTIVE"].includes(sub.status));

        $("invoiceSubscription").innerHTML =
            `<option value="">Select a confirmed subscription</option>` +
            options.map(sub => `
                <option value="${sub.id}">
                    ${escapeHTML(sub.subscription_number)}
                </option>
            `).join("");
    }

    $("showSubscriptionForm").addEventListener("click", async () => {
        await loadPlans();
        await loadProducts();
        $("subscriptionFormCard").classList.remove("hidden");
    });

    $("cancelSubscriptionForm").addEventListener("click", () => {
        $("subscriptionFormCard").classList.add("hidden");
        $("subscriptionForm").reset();
    });

    $("subscriptionForm").addEventListener("submit", async event => {
        event.preventDefault();

        const form = new FormData(event.target);

        const payload = {
            plan_id: Number(form.get("plan_id")),
            start_date: form.get("start_date"),
            expiry_date: form.get("expiry_date") || null,
            lines: [{
                product_id: Number(form.get("product_id")),
                quantity: Number(form.get("quantity")),
                unit_price_minor_units: Number(
                    form.get("unit_price_minor_units")
                ),
                tax_rate_basis_points: Number(
                    form.get("tax_rate_basis_points")
                )
            }]
        };

        try {
            await api("/subscriptions", {
                method: "POST",
                body: JSON.stringify(payload)
            });

            event.target.reset();
            $("subscriptionFormCard").classList.add("hidden");

            message("Subscription created as a draft.");
            await loadSubscriptions();

        } catch (error) {
            message(error.message, "error");
        }
    });

    $("subscriptionsTable").addEventListener("click", async event => {
        const button = event.target.closest("[data-confirm-sub]");

        if (!button) return;

        const id = button.dataset.confirmSub;

        try {
            await api(`/subscriptions/${id}/confirm`, {
                method: "POST"
            });

            message("Subscription confirmed successfully.");
            await loadSubscriptions();

        } catch (error) {
            message(error.message, "error");
        }
    });


    // --------------------------
    // INVOICES
    // --------------------------

    async function loadInvoices() {
        try {
            invoices = await api("/invoices");

            const outstanding = invoices.filter(invoice =>
                Number(invoice.balance_due_minor_units) > 0 &&
                invoice.status !== "CANCELLED"
            );

            $("invoiceCount").textContent = outstanding.length;

            $("invoicesTable").innerHTML = invoices.length
                ? invoices.map(invoice => `
                    <tr>
                        <td><strong>${escapeHTML(invoice.invoice_number)}</strong></td>
                        <td>${escapeHTML(invoice.subscription_id)}</td>
                        <td>${escapeHTML(invoice.issue_date)}</td>
                        <td>${money(invoice.total_amount_minor_units, invoice.currency)}</td>
                        <td>${money(invoice.balance_due_minor_units, invoice.currency)}</td>
                        <td>${statusBadge(invoice.status)}</td>
                        <td>
                            <button class="action-button"
                                    data-view-invoice="${invoice.id}">
                                View
                            </button>
                        </td>
                    </tr>
                `).join("")
                : emptyRow(7, "No invoices found.");

            $("recentInvoices").innerHTML = invoices.length
                ? invoices.slice(0, 5).map(invoice => `
                    <tr>
                        <td>${escapeHTML(invoice.invoice_number)}</td>
                        <td>${escapeHTML(invoice.issue_date)}</td>
                        <td>${money(invoice.total_amount_minor_units, invoice.currency)}</td>
                        <td>${money(invoice.balance_due_minor_units, invoice.currency)}</td>
                        <td>${statusBadge(invoice.status)}</td>
                    </tr>
                `).join("")
                : emptyRow(5, "No recent invoices.");

            updatePaymentOptions();

        } catch (error) {
            message(error.message, "error");
        }
    }

    function updatePaymentOptions() {
        const unpaid = invoices.filter(invoice =>
            Number(invoice.balance_due_minor_units) > 0 &&
            invoice.status === "CONFIRMED"
        );

        $("paymentInvoice").innerHTML =
            `<option value="">Select an unpaid invoice</option>` +
            unpaid.map(invoice => `
                <option value="${invoice.id}">
                    ${escapeHTML(invoice.invoice_number)} —
                    ${money(invoice.balance_due_minor_units, invoice.currency)}
                </option>
            `).join("");
    }

    $("showInvoiceForm").addEventListener("click", async () => {
        await loadSubscriptions();
        $("invoiceFormCard").classList.remove("hidden");
    });

    $("cancelInvoiceForm").addEventListener("click", () => {
        $("invoiceFormCard").classList.add("hidden");
        $("invoiceForm").reset();
    });

    $("invoiceForm").addEventListener("submit", async event => {
        event.preventDefault();

        const form = new FormData(event.target);

        const payload = {
            subscription_id: Number(form.get("subscription_id")),
            billing_period_start: form.get("billing_period_start"),
            billing_period_end: form.get("billing_period_end"),
            due_days: Number(form.get("due_days"))
        };

        try {
            await api("/invoices/generate", {
                method: "POST",
                body: JSON.stringify(payload)
            });

            event.target.reset();
            $("invoiceFormCard").classList.add("hidden");

            message("Invoice generated successfully.");
            await loadInvoices();

        } catch (error) {
            message(error.message, "error");
        }
    });

    $("invoicesTable").addEventListener("click", async event => {
        const button = event.target.closest("[data-view-invoice]");

        if (!button) return;

        try {
            const invoice = await api(
                `/invoices/${button.dataset.viewInvoice}`
            );

            const lines = invoice.lines.map(line =>
                `${line.description || "Product"} — Quantity: ${line.quantity}`
            ).join("\n");

            alert(
                `Invoice: ${invoice.invoice_number}\n` +
                `Status: ${invoice.status}\n` +
                `Total: ${money(invoice.total_amount_minor_units, invoice.currency)}\n` +
                `Balance: ${money(invoice.balance_due_minor_units, invoice.currency)}\n\n` +
                `Items:\n${lines}`
            );

        } catch (error) {
            message(error.message, "error");
        }
    });


    // --------------------------
    // PAYMENTS
    // --------------------------

    $("paymentForm").addEventListener("submit", async event => {
        event.preventDefault();

        const form = new FormData(event.target);

        const payload = {
            invoice_id: Number(form.get("invoice_id")),
            amount_minor_units: Number(form.get("amount_minor_units")),
            payment_method: form.get("payment_method"),
            transaction_reference: form.get("transaction_reference") || null,
            notes: form.get("notes") || null
        };

        try {
            await api("/payments", {
                method: "POST",
                body: JSON.stringify(payload)
            });

            event.target.reset();

            message("Payment record submitted successfully.");
            await loadInvoices();

        } catch (error) {
            message(error.message, "error");
        }
    });


    // --------------------------
    // OVERVIEW
    // --------------------------

    async function loadOverview() {
        try {
            const results = await Promise.all([
                api("/products"),
                api("/plans"),
                api("/subscriptions"),
                api("/invoices")
            ]);

            products = results[0];
            plans = results[1];
            subscriptions = results[2];
            invoices = results[3];

            $("productCount").textContent = products.length;
            $("planCount").textContent = plans.length;
            $("subscriptionCount").textContent = subscriptions.length;

            $("invoiceCount").textContent = invoices.filter(invoice =>
                Number(invoice.balance_due_minor_units) > 0 &&
                invoice.status !== "CANCELLED"
            ).length;

            $("recentSubscriptions").innerHTML = subscriptions.length
                ? subscriptions.slice(0, 5).map(sub => `
                    <tr>
                        <td>${escapeHTML(sub.subscription_number)}</td>
                        <td>${escapeHTML(sub.plan_id)}</td>
                        <td>${escapeHTML(sub.start_date)}</td>
                        <td>${statusBadge(sub.status)}</td>
                    </tr>
                `).join("")
                : emptyRow(4, "No recent subscriptions.");

            $("recentInvoices").innerHTML = invoices.length
                ? invoices.slice(0, 5).map(invoice => `
                    <tr>
                        <td>${escapeHTML(invoice.invoice_number)}</td>
                        <td>${escapeHTML(invoice.issue_date)}</td>
                        <td>${money(invoice.total_amount_minor_units, invoice.currency)}</td>
                        <td>${money(invoice.balance_due_minor_units, invoice.currency)}</td>
                        <td>${statusBadge(invoice.status)}</td>
                    </tr>
                `).join("")
                : emptyRow(5, "No recent invoices.");

        } catch (error) {
            message(error.message, "error");
        }
    }


    // --------------------------
    // LOGOUT
    // --------------------------

    $("logoutButton").addEventListener("click", async () => {
        try {
            await api("/auth/logout", {
                method: "POST"
            });

            window.location.href = "/";

        } catch (error) {
            message(error.message, "error");
        }
    });


    // --------------------------
    // INITIALIZE DASHBOARD
    // --------------------------

    async function initialize() {
        try {
            await loadCurrentUser();
            await loadOverview();
        } catch (error) {
            console.error(error);
        }
    }

    initialize();

});