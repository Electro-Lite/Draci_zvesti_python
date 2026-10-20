import {
  createCipheriv,
  createDecipheriv,
  createHash,
  pbkdf2Sync,
  randomBytes,
} from "node:crypto";
import { basename, extname, resolve } from "node:path";
import {
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  stat,
  unlink,
  writeFile,
} from "node:fs/promises";
import process from "node:process";

const ITERATIONS = 250_000;
const CHUNK_SIZE = 8 * 1024 * 1024;

function parseArgs(values) {
  const options = { output: "dist" };
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index];
    const value = values[index + 1];
    if (!key?.startsWith("--") || !value) {
      throw new Error(`Missing value for ${key || "argument"}`);
    }
    options[key.slice(2)] = value;
  }
  options.windowsInstaller = options["windows-installer"] || options.windows;
  options.windowsPortable = options["windows-portable"];
  if (!options.version || !options.linux || (!options.windowsInstaller && !options.windowsPortable)) {
    throw new Error(
      "Usage: node tools/prepare-release.mjs --version <version> " +
      "[--windows-installer <setup.exe>] [--windows-portable <portable.zip>] " +
      "--linux <game.AppImage> [--output dist]",
    );
  }
  if (!/^\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9.-]+)?$/.test(options.version)) {
    throw new Error(`Invalid version: ${options.version}`);
  }
  return options;
}

async function validateArtifact(path, expectedExtension, label) {
  if (extname(path).toLowerCase() !== expectedExtension.toLowerCase()) {
    throw new Error(`${label} package must have the ${expectedExtension} extension`);
  }
  const details = await stat(path);
  if (!details.isFile() || details.size === 0) {
    throw new Error(`${label} package is missing or empty: ${path}`);
  }
}

async function readPassword() {
  if (!process.stdin.isTTY) {
    const chunks = [];
    for await (const chunk of process.stdin) chunks.push(chunk);
    return Buffer.concat(chunks).toString("utf8").trimEnd();
  }
  return new Promise((resolvePassword, reject) => {
    let password = "";
    process.stdout.write("Release password: ");
    process.stdin.setRawMode(true);
    process.stdin.resume();
    process.stdin.setEncoding("utf8");
    const finish = () => {
      process.stdin.setRawMode(false);
      process.stdin.pause();
      process.stdout.write("\n");
      resolvePassword(password);
    };
    const handleInput = (chunk) => {
      for (const character of chunk) {
        if (character === "\r" || character === "\n") {
          process.stdin.off("data", handleInput);
          finish();
          return;
        }
        if (character === "\u0003") {
          process.stdin.off("data", handleInput);
          process.stdin.setRawMode(false);
          reject(new Error("Cancelled"));
          return;
        }
        password = character === "\u007f" ? password.slice(0, -1) : password + character;
      }
    };
    process.stdin.on("data", handleInput);
  });
}

async function encryptArtifact({
  id,
  platform,
  inputPath,
  password,
  outputDirectory,
  mimeType = "application/octet-stream",
}) {
  const clear = await readFile(inputPath);
  const salt = randomBytes(16);
  const iv = randomBytes(12);
  const key = pbkdf2Sync(password, salt, ITERATIONS, 32, "sha256");
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const ciphertext = Buffer.concat([cipher.update(clear), cipher.final(), cipher.getAuthTag()]);
  const encryptedFiles = [];
  for (let offset = 0, index = 1; offset < ciphertext.length; offset += CHUNK_SIZE, index += 1) {
    encryptedFiles.push(`${id}-release-${String(index).padStart(2, "0")}.enc`);
  }
  await Promise.all(
    encryptedFiles.map((name, index) =>
      writeFile(
        resolve(outputDirectory, name),
        ciphertext.subarray(index * CHUNK_SIZE, (index + 1) * CHUNK_SIZE),
      ),
    ),
  );
  const decipher = createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(ciphertext.subarray(ciphertext.length - 16));
  const verified = Buffer.concat([
    decipher.update(ciphertext.subarray(0, ciphertext.length - 16)),
    decipher.final(),
  ]);
  const sha256 = createHash("sha256").update(clear).digest("hex");
  if (createHash("sha256").update(verified).digest("hex") !== sha256) {
    throw new Error(`${platform} package failed its authenticated round-trip check`);
  }
  return {
    id,
    platform,
    fileName: basename(inputPath),
    encryptedFiles,
    mimeType,
    originalSize: clear.length,
    encryptedSize: ciphertext.length,
    iterations: ITERATIONS,
    salt: salt.toString("base64"),
    iv: iv.toString("base64"),
    sha256,
  };
}

const options = parseArgs(process.argv.slice(2));
const linuxPath = resolve(options.linux);
const windowsInstallerPath = options.windowsInstaller
  ? resolve(options.windowsInstaller)
  : null;
const windowsPortablePath = options.windowsPortable
  ? resolve(options.windowsPortable)
  : null;
if (windowsInstallerPath) {
  await validateArtifact(windowsInstallerPath, ".exe", "Windows installer");
}
if (windowsPortablePath) {
  await validateArtifact(windowsPortablePath, ".zip", "Windows portable package");
}
await validateArtifact(linuxPath, ".AppImage", "Linux");
const password = await readPassword();
if (password.length < 12) throw new Error("Use a release password of at least 12 characters");
const outputDirectory = resolve(options.output);
await mkdir(outputDirectory, { recursive: true });
const stagingDirectory = await mkdtemp(resolve(outputDirectory, ".release-staging-"));
try {
  const artifacts = [];
  if (windowsInstallerPath) {
    artifacts.push(await encryptArtifact({
      id: "windows-installer",
      platform: "Windows 10/11 installer",
      inputPath: windowsInstallerPath,
      password,
      outputDirectory: stagingDirectory,
      mimeType: "application/vnd.microsoft.portable-executable",
    }));
  }
  if (windowsPortablePath) {
    artifacts.push(await encryptArtifact({
      id: "windows-portable",
      platform: "Windows 10/11 portable",
      inputPath: windowsPortablePath,
      password,
      outputDirectory: stagingDirectory,
      mimeType: "application/zip",
    }));
  }
  artifacts.push(await encryptArtifact({
    id: "linux",
    platform: "Linux x86-64",
    inputPath: linuxPath,
    password,
    outputDirectory: stagingDirectory,
  }));
  const metadata = {
    schemaVersion: 2,
    version: options.version,
    publishedAt: new Date().toISOString(),
    artifacts,
  };
  await writeFile(
    resolve(stagingDirectory, "release.json"),
    `${JSON.stringify(metadata, null, 2)}\n`,
  );

  const generated = (await readdir(outputDirectory)).filter((name) =>
    /^(?:game-release(?:-\d+)?|windows(?:-installer|-portable)?-release-\d+|linux-release-\d+)\.enc$/.test(name),
  );
  await Promise.all(generated.map((name) => unlink(resolve(outputDirectory, name))));
  const stagedFiles = await readdir(stagingDirectory);
  for (const name of stagedFiles) {
    await rename(resolve(stagingDirectory, name), resolve(outputDirectory, name));
  }
  console.log(`Prepared and verified release ${options.version} with ${artifacts.length} packages.`);
} finally {
  await rm(stagingDirectory, { recursive: true, force: true });
}
