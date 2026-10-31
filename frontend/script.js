/* ==============================
   BRIGHTLOOP FRONTEND
============================== */

document.addEventListener("DOMContentLoaded", () => {

    // --------------------------
    // ELEMENT REFERENCES
    // --------------------------

    const modal = document.getElementById("authModal");

    const loginButton = document.getElementById("loginButton");
    const registerButton = document.getElementById("registerButton");
    const heroRegisterButton = document.getElementById("heroRegisterButton");
    const aboutRegisterButton = document.getElementById("aboutRegisterButton");
    const ctaRegisterButton = document.getElementById("ctaRegisterButton");

    const footerLoginButton = document.getElementById("footerLoginButton");
    const footerRegisterButton = document.getElementById("footerRegisterButton");

    const closeModalButton = document.getElementById("closeModalButton");

    const loginTab = document.getElementById("loginTab");
    const registerTab = document.getElementById("registerTab");

    const loginForm = document.getElementById("loginForm");
    const registerForm = document.getElementById("registerForm");

    const modalTitle = document.getElementById("modalTitle");
    const modalSubtitle = document.getElementById("modalSubtitle");

    const formMessage = document.getElementById("formMessage");

    const loginSubmitButton = document.getElementById("loginSubmitButton");
    const registerSubmitButton = document.getElementById("registerSubmitButton");

    const mobileMenuButton = document.getElementById("mobileMenuButton");
    const navLinks = document.getElementById("navLinks");


    // --------------------------
    // FOOTER YEAR
    // --------------------------

    document.getElementById("currentYear").textContent =
        new Date().getFullYear();


    // --------------------------
    // MODAL FUNCTIONS
    // --------------------------

    function openModal(mode) {
        modal.classList.add("active");
        modal.setAttribute("aria-hidden", "false");

        document.body.style.overflow = "hidden";

        clearMessage();

        if (mode === "register") {
            showRegisterForm();
        } else {
            showLoginForm();
        }
    }

    function closeModal() {
        modal.classList.remove("active");
        modal.setAttribute("aria-hidden", "true");

        document.body.style.overflow = "";

        clearMessage();
    }


    // --------------------------
    // LOGIN / REGISTER TABS
    // --------------------------

    function showLoginForm() {
        loginForm.classList.remove("hidden");
        registerForm.classList.add("hidden");

        loginTab.classList.add("active");
        registerTab.classList.remove("active");

        modalTitle.textContent = "Welcome back";
        modalSubtitle.textContent =
            "Log in to your Brightloop account.";

        clearMessage();
    }

    function showRegisterForm() {
        registerForm.classList.remove("hidden");
        loginForm.classList.add("hidden");

        registerTab.classList.add("active");
        loginTab.classList.remove("active");

        modalTitle.textContent = "Create your account";
        modalSubtitle.textContent =
            "Get started with Brightloop Software.";

        clearMessage();
    }


    // --------------------------
    // MESSAGE FUNCTIONS
    // --------------------------

    function showMessage(message, type) {
        formMessage.textContent = message;

        formMessage.className = "form-message visible " + type;
    }

    function clearMessage() {
        formMessage.textContent = "";
        formMessage.className = "form-message";
    }


    // --------------------------
    // API ERROR HANDLING
    // --------------------------

    async function getErrorMessage(response) {
        let errorMessage = "Something went wrong. Please try again.";

        try {
            const data = await response.json();

            if (typeof data.detail === "string") {
                errorMessage = data.detail;
            } else if (Array.isArray(data.detail)) {
                errorMessage = data.detail
                    .map(item => item.msg || "Invalid input")
                    .join(". ");
            } else if (typeof data.message === "string") {
                errorMessage = data.message;
            }
        } catch (error) {
            errorMessage = "Server returned an unexpected response.";
        }

        return errorMessage;
    }


    // --------------------------
    // LOADING BUTTON STATE
    // --------------------------

    function setButtonLoading(button, loading, originalText) {
        button.disabled = loading;

        button.textContent = loading
            ? "Please wait..."
            : originalText;
    }


    // --------------------------
    // LOGIN API
    // --------------------------

    loginForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        clearMessage();

        const email = document.getElementById("loginEmail").value.trim();
        const password = document.getElementById("loginPassword").value;

        if (!email || !password) {
            showMessage("Please enter your email and password.", "error");
            return;
        }

        setButtonLoading(loginSubmitButton, true, "Log in");

        try {
            const response = await fetch("/auth/login", {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                credentials: "same-origin",

                body: JSON.stringify({
                    email: email,
                    password: password
                })
            });

            if (!response.ok) {
                const errorMessage = await getErrorMessage(response);

                showMessage(errorMessage, "error");
                return;
            }

            window.location.href = "/dashboard";

        } catch (error) {
            console.error("Login error:", error);

            showMessage(
                "Could not connect to the server. Make sure the FastAPI backend is running.",
                "error"
            );

        } finally {
            setButtonLoading(loginSubmitButton, false, "Log in");
        }
    });


    // --------------------------
    // REGISTER API
    // --------------------------

    registerForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        clearMessage();

        const companyName =
            document.getElementById("registerCompany").value.trim();

        const contactName =
            document.getElementById("registerContact").value.trim();

        const email =
            document.getElementById("registerEmail").value.trim();

        const password =
            document.getElementById("registerPassword").value;

        if (!companyName || !email || !password) {
            showMessage(
                "Please complete all required fields.",
                "error"
            );
            return;
        }

        if (password.length <= 8) {
            showMessage(
                "Your password must contain more than 8 characters.",
                "error"
            );
            return;
        }

        if (!/[A-Z]/.test(password) ||
            !/[a-z]/.test(password) ||
            !/[^A-Za-z0-9]/.test(password)) {

            showMessage(
                "Password must include uppercase, lowercase and a special character.",
                "error"
            );
            return;
        }

        setButtonLoading(
            registerSubmitButton,
            true,
            "Create account"
        );

        try {
            const response = await fetch("/auth/register", {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                credentials: "same-origin",

                body: JSON.stringify({
                    company_name: companyName,
                    contact_name: contactName || null,
                    email: email,
                    password: password
                })
            });

            if (!response.ok) {
                const errorMessage = await getErrorMessage(response);

                showMessage(errorMessage, "error");
                return;
            }

            window.location.href = "/dashboard";

        } catch (error) {
            console.error("Registration error:", error);

            showMessage(
                "Could not connect to the server. Make sure the FastAPI backend is running.",
                "error"
            );

        } finally {
            setButtonLoading(
                registerSubmitButton,
                false,
                "Create account"
            );
        }
    });


    // --------------------------
    // NAVIGATION BUTTONS
    // --------------------------

    loginButton.addEventListener("click", () => {
        openModal("login");
    });

    registerButton.addEventListener("click", () => {
        openModal("register");
    });

    heroRegisterButton.addEventListener("click", () => {
        openModal("register");
    });

    aboutRegisterButton.addEventListener("click", () => {
        openModal("register");
    });

    ctaRegisterButton.addEventListener("click", () => {
        openModal("register");
    });

    footerLoginButton.addEventListener("click", (event) => {
        event.preventDefault();
        openModal("login");
    });

    footerRegisterButton.addEventListener("click", (event) => {
        event.preventDefault();
        openModal("register");
    });


    // --------------------------
    // MODAL CONTROLS
    // --------------------------

    closeModalButton.addEventListener("click", closeModal);

    loginTab.addEventListener("click", showLoginForm);

    registerTab.addEventListener("click", showRegisterForm);

    modal.addEventListener("click", (event) => {
        if (event.target === modal) {
            closeModal();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && modal.classList.contains("active")) {
            closeModal();
        }
    });


    // --------------------------
    // MOBILE NAVIGATION
    // --------------------------

    mobileMenuButton.addEventListener("click", () => {
        const isOpen = navLinks.classList.toggle("mobile-open");

        mobileMenuButton.setAttribute(
            "aria-expanded",
            String(isOpen)
        );
    });

    navLinks.querySelectorAll("a").forEach(link => {
        link.addEventListener("click", () => {
            navLinks.classList.remove("mobile-open");
            mobileMenuButton.setAttribute("aria-expanded", "false");
        });
    });

});