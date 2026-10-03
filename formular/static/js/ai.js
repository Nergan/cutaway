(function () {
    const button = document.getElementById("aiLanguageRun");
    const input = document.getElementById("aiLanguageText");
    const output = document.getElementById("aiLanguageResult");
    if (!button || !input || !output) return;

    button.addEventListener("click", async () => {
        const text = input.value.trim();
        output.textContent = "";
        if (!text) {
            output.textContent = "Text is required.";
            return;
        }
        button.disabled = true;
        try {
            const response = await fetch("/formular/api/ai/language", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({text})
            });
            const payload = await response.json();
            if (!response.ok) {
                output.textContent = typeof payload.detail === "string" ? payload.detail : "Detection failed.";
                return;
            }
            output.textContent = "AI · " + payload.language + " · " + payload.model.id;
        } catch (error) {
            output.textContent = "Detection failed.";
        } finally {
            button.disabled = false;
        }
    });
}());