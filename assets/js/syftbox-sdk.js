// syftbox-sdk.js
(function () {
  const LOCALHOST_URL = "http://localhost:7938/";
  const INSTALL_URL = "https://syftbox.net/";
  const SYFTBOX_ICON_URL = "https://raw.githubusercontent.com/madhavajay/youtube-wrapped/refs/heads/main/assets/images/syftbox_icon.png";

  // Function to extract token from URL hash and store it in localStorage
  function extractTokenFromUrl() {
    const hash = window.location.hash;
    const tokenMatch = hash.match(/#token=([a-zA-Z0-9]+)/);
    if (tokenMatch) {
      const token = tokenMatch[1];
      localStorage.setItem("syft_token", token);
      console.log("Extracted Token:", token);
    } else {
      console.log("No token found in URL hash.");
    }
  }

  // Extract token from URL on page load
  extractTokenFromUrl();

  function getGitHubRawUrl(githubUrl) {
    return (
      githubUrl
        .replace("github.com", "raw.githubusercontent.com")
        .replace(/\/$/, "") + "/main/README.md"
    );
  }

  async function parseGitHubReadme(githubUrl) {
    try {
      const rawUrl = getGitHubRawUrl(githubUrl);
      const response = await fetch(rawUrl);

      if (!response.ok) {
        const masterUrl = rawUrl.replace("/main/", "/master/");
        const masterResponse = await fetch(masterUrl);
        if (!masterResponse.ok) {
          throw new Error("Failed to fetch README");
        }
        return parseFrontmatter(await masterResponse.text());
      }

      return parseFrontmatter(await response.text());
    } catch (error) {
      console.error("Error fetching GitHub README:", error);
      return null;
    }
  }

  function parseFrontmatter(content) {
    try {
      const frontmatterRegex = /^---\n([\s\S]*?)\n---/;
      const match = content.match(frontmatterRegex);

      if (!match) return null;

      const frontmatter = match[1];
      const parsed = {};

      frontmatter.split("\n").forEach((line) => {
        const [key, ...valueParts] = line.split(":");
        if (key && valueParts.length) {
          const value = valueParts
            .join(":")
            .trim()
            .replace(/^"(.*)"$/, "$1");
          parsed[key.trim()] = value;
        }
      });

      return parsed;
    } catch (error) {
      console.error("Error parsing frontmatter:", error);
      return null;
    }
  }

  let sdkReady;
  const APIBadgeSDK = {
    initialized: new Promise((resolve) => {
      sdkReady = resolve;
    }),

    init() {
      const styles = `
          .api-badge {
              display: inline-flex;
              align-items: center;
              gap: 12px;
              padding: 10px 16px;
              border-radius: 10px;
              font-size: 14px;
              font-weight: 500;
              color: white;
              border: none;
              cursor: pointer;
              transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
              text-decoration: none;
              box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
              position: relative;
              overflow: hidden;
              justify-content: flex-start;
          }

          .api-badge::before {
              content: "";
              position: absolute;
              top: 0;
              left: 0;
              right: 0;
              bottom: 0;
              background: linear-gradient(rgba(255, 255, 255, 0.1),rgba(255, 255, 255, 0));
              opacity: 0;
              transition: opacity 0.3s ease;
          }

          .api-badge:disabled {
              opacity: 0.7;
              cursor: not-allowed;
          }

          .api-badge.installed {
              background-color: #16a34a;
              cursor: pointer;
          }

          .api-badge.update {
              background-color: #f59e0b;
          }

          .api-badge.install {
              background-color: #2563eb;
          }

          .api-badge.error {
              background-color: #dc2626;
          }

          .api-badge.checking {
              background-color: #4b5563;
              cursor: wait;
          }

          .api-badge:not(:disabled):hover {
              transform: translateY(-2px);
              box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
          }

          .api-badge:not(:disabled):hover::before {
              opacity: 1;
          }

          .api-badge:not(:disabled):active {
              transform: translateY(1px);
              box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
          }

          .api-badge img {
              width: 20px;
              height: 20px;
              border-radius: 4px;
              flex-shrink: 0;
          }

          .api-badge .version {
              font-size: 12px;
              opacity: 0.9;
          }

          .api-badge .content {
              display: flex;
              align-items: center;
              gap: 4px;
              flex: 1;
              min-width: 0;
          }

          .status-pill {
              background-color: rgba(0, 0, 0, 0.2);
              padding: 3px 10px;
              border-radius: 12px;
              font-size: 12px;
              margin-left: auto;
              backdrop-filter: blur(4px);
              transition: all 0.3s ease;
              flex-shrink: 0;
          }

          .api-badge:not(:disabled):hover .status-pill {
              background-color: rgba(0, 0, 0, 0.3);
          }

          @keyframes spin {
              to {
                  transform: rotate(360deg);
              }
          }

          .loading-icon {
              animation: spin 1s linear infinite;
          }
      `;

      const styleSheet = document.createElement("style");
      styleSheet.textContent = styles;
      document.head.appendChild(styleSheet);

      sdkReady();
      return this;
    },

    async show(...args) {
      await this.initialized;

      // Check if only GitHub URL is provided
      if (
        args.length === 1 &&
        typeof args[0] === "string" &&
        args[0].includes("github.com")
      ) {
        const githubUrl = args[0];
        const metadata = await parseGitHubReadme(githubUrl);

        if (!metadata) {
          console.error("Failed to parse GitHub README metadata");
          return;
        }

        const { name, version, icon } = metadata;
        if (!name || !version) {
          console.error(
            "Required metadata (name, version) not found in README"
          );
          return;
        }

        return this._show(name, version, githubUrl, icon);
      }

      // Traditional initialization with explicit parameters
      const [apiName, version, source, iconUrl] = args;
      return this._show(apiName, version, source, iconUrl);
    },

    async _show(apiName, version, source, iconUrl = null) {
      const container = document.getElementById("syftbox-api-badge");
      if (!container) {
        console.error("Container element #syftbox-api-badge not found");
        return;
      }

      this.renderBadge(
        "checking",
        "Checking...",
        apiName,
        version,
        null,
        SYFTBOX_ICON_URL
      );

      try {
        const syftToken = localStorage.getItem("syft_token");
        console.debug("Syft Token:", syftToken);

        const response = await fetch(
          `${LOCALHOST_URL}v1/app/list`,
          {
            method: "GET",
            headers: {
              "Authorization": `Bearer ${syftToken}`,
              "Accept": "application/json"
            }
          }
        );

        const data = await response.json();
        if (response.status === 401) {
          console.error("No token found, please login.");
          this.renderBadge(
            "login",
            "Login",
            "",
            "",
            () => {
              const redirect_url = window.location.href;
              const syft_url = `syft://controlplane/get_token?redirect=${encodeURIComponent(redirect_url)}`;
              window.open(syft_url, "_blank");
            },
            SYFTBOX_ICON_URL
          );
          return;
        }

        if (response.ok && data.apps && data.apps.includes(apiName)) {
          this.renderBadge(
            "installed",
            "Installed",
            apiName,
            version,
            () => window.open(source, "_blank"),
            SYFTBOX_ICON_URL
          );
        } else if (response.ok) {
          this.renderBadge(
            "install",
            "Install",
            apiName,
            version,
            () => this.installAPI(apiName, source, version, iconUrl),
            SYFTBOX_ICON_URL
          );
        } else {
          console.error("Error response received, please install SyftBox.");
          this.renderBadge(
            "install-syftbox",
            "Install SyftBox",
            "",
            "",
            () => window.open(INSTALL_URL, "_blank"),
            SYFTBOX_ICON_URL
          );
        }
      } catch (error) {
        console.error("Error fetching API status:", error);
        this.renderBadge(
          "install-syftbox",
          "Install SyftBox",
          "",
          "",
          () => window.open(INSTALL_URL, "_blank"),
          SYFTBOX_ICON_URL
        );
      }
    },

    renderBadge(
      status,
      statusText,
      apiName,
      version,
      onClick = null,
      iconUrl = null
    ) {
      const container = document.getElementById("syftbox-api-badge");
      const isInteractive = status !== "checking";

      const defaultIcon = SYFTBOX_ICON_URL;
      const finalIconUrl = iconUrl || defaultIcon;

      container.innerHTML = `
          <button class="api-badge ${status}" ${!isInteractive ? "disabled" : ""
        }>
              <img src="${finalIconUrl}" alt="${apiName} icon">
              <div class="content">
                  <span>${apiName}</span>
                  <span class="version">${version}</span>
                  <span class="status-pill">${statusText}</span>
              </div>
          </button>
      `;

      if (onClick) {
        container
          .querySelector(".api-badge")
          .addEventListener("click", onClick);
      }
    },

    async installAPI(apiName, source, version, iconUrl = null) {
      const button = document.querySelector(".api-badge");
      const originalContent = button.innerHTML;
      button.disabled = true;

      const finalIconUrl = SYFTBOX_ICON_URL;

      button.innerHTML = `
          <img src="${finalIconUrl}" alt="API icon" class="loading-icon">
          <div class="content">
              <span>Installing...</span>
          </div>
      `;

      try {
        const syftToken = localStorage.getItem("syft_token"); // Retrieve syftToken from localStorage
        const requestBody = {
          branch: "main",
          force: true,
          repoURL: source // Use source as repoURL
        };

        console.log("Request Body:", requestBody);

        const response = await fetch(`${LOCALHOST_URL}v1/app/install`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${syftToken}` // Include syftToken in headers
          },
          body: JSON.stringify(requestBody),
        });

        if (response.status === 200) {
          this.show(apiName, version, source, iconUrl);
        } else {
          throw new Error("Installation failed");
        }
      } catch (error) {
        console.error("Error installing API:", error);
        this.renderBadge(
          "install-syftbox",
          "Install SyftBox",
          "SyftBox",
          "Latest",
          () => window.open("https://syftbox.net/", "_blank"),
          iconUrl
        );
      }
    },
  };

  // Initialize and expose the SDK
  window.APIBadge = APIBadgeSDK.init();
})();
