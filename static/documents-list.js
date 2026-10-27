"use strict";

(function () {
    const params = new URLSearchParams(location.search);
    const categoryId = params.get("category_id") || "";
    const label = params.get("label") || "文書一覧";

    document.title = label;
    const titleEl = document.getElementById("list-title");
    if (titleEl) titleEl.textContent = label;

    if (!categoryId) {
        const list = document.getElementById("file-list");
        const li = document.createElement("li");
        li.className = "no-files-msg";
        li.textContent = "カテゴリが指定されていません";
        list.appendChild(li);
        return;
    }

    fetch("/api/documents/files?category_id=" + encodeURIComponent(categoryId))
        .then(function (res) { return res.json(); })
        .then(function (files) {
            const list = document.getElementById("file-list");
            if (files.length === 0) {
                const li = document.createElement("li");
                li.className = "no-files-msg";
                li.textContent = "PDFファイルがありません";
                list.appendChild(li);
                return;
            }
            files.forEach(function (name) {
                const li = document.createElement("li");
                li.className = "file-list-item";
                li.textContent = name;
                li.addEventListener("click", function () {
                    const p = new URLSearchParams({
                        category_id: categoryId,
                        file: name + ".pdf",
                        label: label,
                    });
                    window.location.href = "/documents/viewer?" + p.toString();
                });
                list.appendChild(li);
            });
        })
        .catch(function () {
            const list = document.getElementById("file-list");
            const li = document.createElement("li");
            li.className = "no-files-msg";
            li.textContent = "ファイル一覧の取得に失敗しました";
            list.appendChild(li);
        });
}());
