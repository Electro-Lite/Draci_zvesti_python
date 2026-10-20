const passwordInput = document.querySelector("#release-password");
const togglePassword = document.querySelector("#toggle-password");
const downloadButtons = [...document.querySelectorAll(".download-button")];
const statusMessage = document.querySelector("#status-message");
const progressWrap = document.querySelector("#progress-wrap");
const progressLabel = document.querySelector("#progress-label");

let release = null;

function decodeBase64(value) {
  return Uint8Array.from(atob(value), (character) => character.charCodeAt(0));
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  const unit = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** unit).toFixed(unit ? 1 : 0)} ${units[unit]}`;
}

function setStatus(message, type = "") {
  statusMessage.textContent = message;
  statusMessage.className = `status-message ${type}`.trim();
}

function setBusy(busy, message = "Preparing secure download…") {
  passwordInput.disabled = busy;
  togglePassword.disabled = busy;
  downloadButtons.forEach((button) => {
    button.disabled = busy || !release;
  });
  progressWrap.hidden = !busy;
  progressLabel.textContent = message;
}

async function loadRelease() {
  try {
    const response = await fetch("release.json", { cache: "no-store" });
    if (!response.ok) throw new Error("No release metadata is published");
    release = await response.json();
    if (release.schemaVersion !== 2 || !Array.isArray(release.artifacts)) {
      throw new Error("No playable release is published");
    }
    document.querySelector("#release-version").textContent = `Version ${release.version}`;
    document.querySelector("#release-date").textContent = new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    }).format(new Date(release.publishedAt));
    for (const card of document.querySelectorAll(".platform-card")) {
      const artifact = release.artifacts.find((item) => item.id === card.dataset.platform);
      if (!artifact) {
        card.querySelector(".package-name").textContent = "Not included in this release";
        card.querySelector(".package-size").textContent = "—";
        card.querySelector(".download-button").disabled = true;
        continue;
      }
      card.querySelector(".package-name").textContent = artifact.fileName;
      card.querySelector(".package-size").textContent = formatBytes(artifact.originalSize);
      card.querySelector(".download-button").disabled = false;
    }
  } catch (error) {
    release = null;
    document.querySelector("#release-version").textContent = "Release unavailable";
    setStatus("Playable Windows and Linux packages have not been published yet.", "error");
    setBusy(false);
  }
}

async function deriveKey(password, salt, iterations) {
  const material = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations, hash: "SHA-256" },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["decrypt"],
  );
}

async function unlockDownload(password, artifact) {
  setBusy(true, "Downloading encrypted package…");
  setStatus("Keep this tab open while the package is decrypted.");
  try {
    const encryptedFiles = artifact.encryptedFiles;
    const encryptedParts = [];
    let encryptedLength = 0;
    for (const [index, fileName] of encryptedFiles.entries()) {
      progressLabel.textContent = `Downloading encrypted package… ${index + 1}/${encryptedFiles.length}`;
      const response = await fetch(fileName, { cache: "no-store" });
      if (!response.ok) throw new Error("The encrypted package is unavailable");
      const part = new Uint8Array(await response.arrayBuffer());
      encryptedParts.push(part);
      encryptedLength += part.length;
    }
    const encrypted = new Uint8Array(encryptedLength);
    let offset = 0;
    for (const part of encryptedParts) {
      encrypted.set(part, offset);
      offset += part.length;
    }
    progressLabel.textContent = "Checking password and decrypting locally…";
    const key = await deriveKey(
      password,
      decodeBase64(artifact.salt),
      artifact.iterations,
    );
    const clear = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: decodeBase64(artifact.iv), tagLength: 128 },
      key,
      encrypted.buffer,
    );
    const blob = new Blob([clear], { type: artifact.mimeType || "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = artifact.fileName;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
    passwordInput.value = "";
    setStatus("Unlocked. Your download has started.", "success");
  } catch (error) {
    const wrongPassword = error?.name === "OperationError";
    setStatus(
      wrongPassword
        ? "That password did not unlock this release. Please try again."
        : "The protected package could not be downloaded. Please try again later.",
      "error",
    );
    passwordInput.focus();
    passwordInput.select();
  } finally {
    setBusy(false);
  }
}

togglePassword.addEventListener("click", () => {
  const showing = passwordInput.type === "text";
  passwordInput.type = showing ? "password" : "text";
  togglePassword.textContent = showing ? "Show" : "Hide";
  togglePassword.setAttribute("aria-label", showing ? "Show password" : "Hide password");
  passwordInput.focus();
});

downloadButtons.forEach((button) => button.addEventListener("click", () => {
  if (!release || !passwordInput.value) {
    setStatus("Enter the release password first.", "error");
    passwordInput.focus();
    return;
  }
  const platform = button.closest(".platform-card").dataset.platform;
  const artifact = release.artifacts.find((item) => item.id === platform);
  if (!artifact) return;
  unlockDownload(passwordInput.value, artifact);
}));

setBusy(false);
loadRelease();
