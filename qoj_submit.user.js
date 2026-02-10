// ==UserScript==
// @name         QOJ WS Submit Bridge
// @namespace    https://qoj.ac/
// @version      0.2.2
// @description  Receive code over WebSocket and auto-submit on QOJ
// @match        https://qoj.ac/contest/*
// @grant        none
// @author       minstdfx
// @run-at       document-end
// ==/UserScript==

(function () {
  "use strict";

  if (!location.pathname.match(/^\/contest\/\d*$/)) return;

  const WS_URL = "ws://127.0.0.1:8000/ws";
  const HTTP_BASE = WS_URL.replace(/^ws/, "http").replace(/\/ws$/, "");
  const REPORT_URL = `${HTTP_BASE}/submission-report`;
  const SCORE_URL = `${HTTP_BASE}/submission-score`;
  let socket;
  let previewRoot;
  let previewFrame;
  let lastPayload;
  let previewWrapper;
  let submissionsOpenTimer;
  let submissionAlreadyOpened = false;
  let submissionReportSent = false;
  let submissionsNavigateTimer;
  let scorePollTimer;

  function log(msg) {
    console.log("[qoj-bridge]", msg);
  }

  function ensurePreview() {
    if (previewRoot) return previewRoot;

    const root = document.createElement("div");
    root.id = "qoj-ws-preview";
    root.style.position = "fixed";
    root.style.top = "0";
    root.style.left = "0";
    root.style.width = "100%";
    root.style.height = "100%";
    root.style.background = "rgba(0,0,0,0.5)";
    root.style.zIndex = "9999";
    root.style.display = "none";
    root.style.alignItems = "center";
    root.style.justifyContent = "center";

    const box = document.createElement("div");
    box.style.background = "#111";
    box.style.color = "#f5f5f5";
    box.style.border = "1px solid #333";
    box.style.borderRadius = "8px";
    box.style.boxShadow = "0 8px 30px rgba(0,0,0,0.4)";
    box.style.width = "80%";
    box.style.maxWidth = "960px";
    box.style.maxHeight = "80%";
    box.style.display = "flex";
    box.style.flexDirection = "column";

    const header = document.createElement("div");
    header.style.display = "flex";
    header.style.justifyContent = "space-between";
    header.style.alignItems = "center";
    header.style.padding = "12px 16px";
    header.style.borderBottom = "1px solid #333";

    const title = document.createElement("div");
    title.textContent = "QOJ WebSocket Preview";
    title.style.fontWeight = "bold";

    const closeBtn = document.createElement("button");
    closeBtn.textContent = "Close";
    closeBtn.style.background = "#444";
    closeBtn.style.color = "#fff";
    closeBtn.style.border = "1px solid #666";
    closeBtn.style.borderRadius = "4px";
    closeBtn.style.padding = "6px 10px";
    closeBtn.style.cursor = "pointer";
    closeBtn.addEventListener("click", () => {
      root.style.display = "none";
    });

    header.appendChild(title);
    header.appendChild(closeBtn);

    const meta = document.createElement("div");
    meta.style.padding = "10px 16px";
    meta.style.fontSize = "14px";
    meta.style.borderBottom = "1px solid #333";

    const codeBox = document.createElement("pre");
    codeBox.style.margin = "0";
    codeBox.style.padding = "12px 16px";
    codeBox.style.flex = "1";
    codeBox.style.overflow = "auto";
    codeBox.style.fontSize = "13px";
    codeBox.style.background = "#0b0b0b";
    codeBox.style.borderRadius = "0 0 8px 8px";

    box.appendChild(header);
    box.appendChild(meta);
    box.appendChild(codeBox);
    root.appendChild(box);
    document.body.appendChild(root);

    previewRoot = { root, meta, codeBox };
    return previewRoot;
  }

  function showPreview(payload) {
    const { root, meta, codeBox } = ensurePreview();
    const { problemCode, language, code, timestamp } = payload;
    meta.textContent = `Problem: ${problemCode || "?"} | Lang: ${language || "?"} | Time: ${timestamp || ""}`;
    codeBox.textContent = code || "<empty>";
    root.style.display = "flex";
  }

  function extractSubmissionInfo(cw) {
    const jq = cw.$;
    if (!jq) return null;
    const rows = jq("tbody>tr");
    const row = rows && rows.length ? rows[0] : null;
    if (!row || !row.children || row.children.length < 7) return null;
    const sid = row.children[0]?.innerText || "";
    const surl = jq(row.children[0]).find("a").attr("href") || "";
    const stime = row.children[row.children.length - 1]?.innerText || "";
    if (!sid || !surl || !stime) return null;
    return { sid, surl, stime };
  }

  function reportSubmissionInfo(info) {
    const jq = window.$;
    if (!lastPayload || !lastPayload.requestId) return;
    submissionReportSent = true;
    const body = new URLSearchParams({
      request_id: lastPayload.requestId,
      sid: info.sid,
      surl: info.surl,
      stime: info.stime,
    });
    console.log("info:", info);
    fetch(REPORT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    }).catch((err) => log("reportSubmissionInfo error: " + err.message));
  }

  function notifyServerScore(sid, status) {
    const body = new URLSearchParams({ sid, status });
    fetch(SCORE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    }).catch((err) => log("notifyServerScore error: " + err.message));
  }

  function startScoreWatch(info) {
    if (!info || !info.surl || !info.sid) return;
    const jq = window.$;
    if (!jq) return;
    if (scorePollTimer) clearInterval(scorePollTimer);
    scorePollTimer = setInterval(async () => {
      try {
        const res = await fetch(info.surl, { method: "GET", credentials: "same-origin" });
        const data = await res.text();
        const score = jq(jq(data).find("table td")[3]);
        const inner = score && score.children().length ? score.children()[0].innerHTML : "";
        console.log("score poll:", inner);
        if (inner && inner.trim() !== "Waiting" && inner.trim() !== "Judging") {
          clearInterval(scorePollTimer);
          scorePollTimer = null;
          notifyServerScore(info.sid, inner.trim());
        }
      } catch (err) {
        console.log(`score poll error: ${String(err)}`);
      }
    }, 3000);
  }

  function fillFrameEditor() {
    if (!previewFrame || !lastPayload) return;
    if (previewFrame.contentWindow?.location?.href === "about:blank") return;
    const cw = previewFrame.contentWindow;
    if (!cw || !cw.document) return;

    try {
      const jq = cw.$;
      if (!jq) {
        log("jquery not found in iframe");
        return;
      }
      const useFileUpload = (() => {
        const div = jq("#div-answer_answer_file");
        return div && div.length && div.css("display") !== "none";
      })();
      setAnswerLanguage(cw);
      const tab = jq("a[href='#tab-submit-answer']");
      if (tab && tab.length) {
          console.log("find element", tab[0]);
          tab[0].click();
      }
      if (useFileUpload) {
        const fileInput = jq("#input-answer_answer_file")[0];
        if (fileInput) {
          const blob = new cw.Blob([lastPayload.code || ""], { type: "text/plain" });
          const newFile = new cw.File([blob], "qwq.cpp", { type: blob.type });
          const dataTransfer = new cw.DataTransfer();
          // keep existing files if any
          Array.from(fileInput.files || []).forEach((f) => dataTransfer.items.add(f));
          dataTransfer.items.add(newFile);
          fileInput.files = dataTransfer.files;
        }
      } else {
        const editor = jq("#input-answer_answer_editor");
        if (editor && editor.length) {
          editor.val(lastPayload.code || "");
          editor.trigger("input");
        }
      }
      const submitBtn = jq("#button-submit-answer");
      if (submitBtn && submitBtn.length) submitBtn[0].click();
      // keep iframe open for debugging; no auto navigation
      if (submissionsNavigateTimer) clearTimeout(submissionsNavigateTimer);
      submissionsNavigateTimer = setTimeout(goToSubmissionsPage, 1000);
    } catch (err) {
      log("fillFrameEditor error: " + err.message);
    }
  }

  // keep iframe open for debugging; disable auto-close
  function closeFrameAndOpenSubmissions() {
    if (submissionAlreadyOpened) return;
    submissionAlreadyOpened = true;
    if (submissionsOpenTimer) {
      clearTimeout(submissionsOpenTimer);
      submissionsOpenTimer = null;
    }
    if (submissionsNavigateTimer) {
      clearTimeout(submissionsNavigateTimer);
      submissionsNavigateTimer = null;
    }
    if (previewWrapper && previewWrapper.parentNode) {
      previewWrapper.parentNode.removeChild(previewWrapper);
    }
    previewFrame = null;
    previewWrapper = null;
  }

  function openProblemFrame(problemCode, codeText, language, requestId) {
    lastPayload = { problemCode, code: codeText, language, requestId };
    submissionAlreadyOpened = false;
    submissionReportSent = false;
    if (submissionsOpenTimer) {
      clearTimeout(submissionsOpenTimer);
      submissionsOpenTimer = null;
    }
    if (submissionsNavigateTimer) {
      clearTimeout(submissionsNavigateTimer);
      submissionsNavigateTimer = null;
    }
    const targetProblem = problemCode || "A";
    const cid = currentContestId();
    const table = document.querySelector(".table-responsive");
    let src = cid ? `${location.origin}/contest/${cid}/problem/${targetProblem}` : location.href;
    if (table) {
      const anchor = table.querySelectorAll("a")[targetProblem.charCodeAt(0) - "A".charCodeAt(0)];
      if (anchor && anchor.href) src = anchor.href;
    }

    if (!previewFrame) {
      const wrapper = document.createElement("div");
      wrapper.style.width = "100%";
      wrapper.style.height = "480px";
      wrapper.style.marginTop = "16px";
      wrapper.style.border = "1px solid #ccc";
      wrapper.style.borderRadius = "4px";
      wrapper.style.overflow = "hidden";
      wrapper.style.boxShadow = "0 4px 18px rgba(0,0,0,0.18)";

      const frame = document.createElement("iframe");
      frame.style.width = "100%";
      frame.style.height = "100%";
      frame.style.border = "0";

      frame.addEventListener("load", handleFrameLoad);

      wrapper.appendChild(frame);
      document.body.appendChild(wrapper);
      previewFrame = frame;
      previewWrapper = wrapper;
    }
    previewFrame.src = src;
    if (previewFrame.contentDocument && previewFrame.contentDocument.readyState === "complete") {
      handleFrameLoad();
    }
  }

  function handleFrameLoad() {
    if (!previewFrame) return;
    const cw = previewFrame.contentWindow;
    if (!cw || !cw.document) return;
    const path = cw.location?.pathname || "";
    if (/\/submissions/.test(path)) {
      if (!submissionReportSent) {
        const info = extractSubmissionInfo(cw);
        console.log("extracted info:", info);
        if (info) {
          reportSubmissionInfo(info);
          startScoreWatch(info);
        }
      }
      if (submissionsOpenTimer) clearTimeout(submissionsOpenTimer);
      submissionsOpenTimer = setTimeout(closeFrameAndOpenSubmissions, 400);
      // stay on submissions page for debugging; do not auto-close iframe
      return;
    }
    fillFrameEditor();
  }

  function goToSubmissionsPage() {
    // disabled for debugging; keep iframe on problem page
  }

  function currentContestId() {
    const parts = window.location.pathname.split("/").filter(Boolean);
    const idx = parts.indexOf("contest");
    return idx >= 0 && parts[idx + 1] ? parts[idx + 1] : null;
  }

  function currentProblemCode() {
    const parts = window.location.pathname.split("/").filter(Boolean);
    const idx = parts.indexOf("problem");
    return idx >= 0 && parts[idx + 1] ? parts[idx + 1] : null;
  }

  function setLanguage(lang) {
    const select = document.querySelector("select[name='language'], select#language");
    if (select) {
      select.value = lang;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function setAnswerLanguage(cw) {
    const langValue = (lastPayload && lastPayload.language) || "C++26";
    const jq = cw.$;
    if (!jq) return;
    const input = jq("#input-answer_answer_language");
    if (input && input.length && input[0]) {
      input[0].value = langValue;
      input.trigger("input");
      input.trigger("change");
    }
  }

  function setCode(value) {
    if (window.monaco && monaco.editor && monaco.editor.getModels().length) {
      const model = monaco.editor.getModels()[0];
      model.setValue(value);
      return true;
    }
    const cm = document.querySelector(".CodeMirror");
    if (cm && cm.CodeMirror) {
      cm.CodeMirror.setValue(value);
      return true;
    }
    const textarea = document.querySelector("textarea[name='code'], textarea#code, textarea");
    if (textarea) {
      textarea.value = value;
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
      return true;
    }
    return false;
  }

  function clickSubmit() {
    const button = Array.from(document.querySelectorAll("button, input[type='submit']"))
      .find((el) => /submit|提交/i.test(el.textContent || el.value || ""));
    if (button) button.click();
  }

  function handleMessage(event) {
    const data = JSON.parse(event.data || "{}{}");
    const { problemCode, language, code, requestId } = data;
    if (!problemCode || !code) return;
    const pageProblem = currentProblemCode();
    if (pageProblem && pageProblem !== problemCode) return;
    // showPreview({ contestId, problemCode, language, code, timestamp: data.timestamp });
    openProblemFrame(problemCode, code, language, requestId);
    log(`previewing code for problem ${problemCode}`);
  }

  function setupWebSocket() {
    socket = new WebSocket(WS_URL);
    socket.addEventListener("open", () => log("connected"));
    socket.addEventListener("message", handleMessage);
    socket.addEventListener("close", () => {
      log("socket closed, retrying in 3s");
      setTimeout(setupWebSocket, 3000);
    });
    socket.addEventListener("error", (e) => {
      log("socket error: " + e.message);
      socket.close();
    });
  }

  setupWebSocket();
})();
