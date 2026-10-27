"use strict";

(async function () {
    let data = { button_count: 3, categories: [] };
    try {
        const res = await fetch("/api/documents/categories");
        if (res.ok) data = await res.json();
    } catch (_) {}

    const buttonCount = Math.min(Math.max(parseInt(data.button_count) || 3, 1), 5);
    const categories = data.categories || [];
    const container = document.getElementById("categories-container");

    for (let i = 0; i < buttonCount; i++) {
        const cat = categories[i] || { label: "分類" + (i + 1), folder: "" };
        const btn = document.createElement("button");
        btn.className = "doc-category-btn";
        btn.textContent = cat.label || "分類" + (i + 1);
        btn.disabled = !cat.folder;
        if (cat.folder) {
            const categoryId = i;
            const label = cat.label || "分類" + (i + 1);
            btn.addEventListener("click", function () {
                const params = new URLSearchParams({ category_id: categoryId, label: label });
                window.location.href = "/documents/list?" + params.toString();
            });
        }
        container.appendChild(btn);
    }
}());
