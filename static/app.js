const messages = document.getElementById("messages");
const form = document.getElementById("chat-form");
const input = document.getElementById("chat-input");
const fileInput = document.getElementById("file-input");
const uploadLabel = document.getElementById("upload-label");
const documents = document.getElementById("documents");
const status = document.getElementById("status");

function addMessage(role, text) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.innerHTML = `<div class="avatar">${role === "user" ? "You" : "KA"}</div><div class="bubble"></div>`;
  article.querySelector(".bubble").textContent = text;
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
}

async function loadDocuments() {
  const response = await fetch("/api/documents");
  const items = await response.json();
  documents.replaceChildren();
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "document";
    row.innerHTML = `<span class="document-name" title="${item.name}">${item.name}</span><button type="button" aria-label="Delete">×</button>`;
    row.querySelector("button").addEventListener("click", async () => {
      await fetch(`/api/documents/${item.id}`, { method: "DELETE" });
      loadDocuments();
    });
    documents.appendChild(row);
  });
}

fileInput.addEventListener("change", async () => {
  if (!fileInput.files.length) return;
  const file = fileInput.files[0];
  uploadLabel.textContent = "Uploading...";
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/documents", { method: "POST", body });
  if (response.ok) {
    const result = await response.json();
    uploadLabel.textContent = `+ ${result.name}`;
    addMessage("assistant", `I indexed "${result.name}" and it is ready for questions.`);
    loadDocuments();
  } else {
    const error = await response.json();
    uploadLabel.textContent = "+ Upload document";
    addMessage("assistant", error.detail || "Upload failed.");
  }
  fileInput.value = "";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  addMessage("user", question);

  const submitButton = form.querySelector("button");
  submitButton.disabled = true;
  submitButton.textContent = "...";
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Request failed.");
    const suffix = result.sources?.length ? `\n\nSources: ${result.sources.join(", ")}` : "";
    addMessage("assistant", result.answer + suffix);
    status.textContent = result.mode === "ai" ? "AI mode" : "Local mode";
  } catch (error) {
    addMessage("assistant", error.message);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Send";
  }
});
