class Chatbox {
  constructor() {
    this.args = {
      openButton: document.querySelector(".chatbox__button"),
      chatbox: document.querySelector(".chatbox__support"),
      sendButton: document.querySelector(".send__button"),
      langButtons: document.querySelectorAll(".lang-button"),
      langContainer: document.querySelector(".language-selection"),
      inputField: document.querySelector(".chatbox__footer input"),
    };
    this.state = false;
    this.messages = [];
  }

  display() {
    const {
      openButton,
      chatbox,
      sendButton,
      langButtons,
      langContainer,
      inputField,
    } = this.args;

    openButton.addEventListener("click", () => this.toggleState(chatbox));

    sendButton.addEventListener("click", () => this.onSendButton(chatbox));

    inputField.addEventListener("keyup", ({ key }) => {
      if (key === "Enter") {
        this.onSendButton(chatbox);
      }
    });

    langButtons.forEach((button) => {
      button.addEventListener("click", () =>
        this.onLangButton(chatbox, button.dataset.lang)
      );
    });

    openButton.addEventListener("click", () => {
      if (this.state) {
        this.checkState(chatbox);
      }
    });
  }

  toggleState(chatbox) {
    this.state = !this.state;
    if (this.state) {
      chatbox.classList.add("chatbox--active");
    } else {
      chatbox.classList.remove("chatbox--active");
    }
  }

  checkState(chatbox) {
    fetch($SCRIPT_ROOT + "/predict", {
      method: "POST",
      body: JSON.stringify({ message: "get_state" }),
      mode: "cors",
      headers: { "Content-Type": "application/json" },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`);
        return r.json();
      })
      .then((r) => {
        if (r.state === "language") {
          this.args.langContainer.style.display = "flex";
          this.args.inputField.style.display = "none";
          this.args.sendButton.style.display = "none";
          this.args.inputField.removeAttribute("dir");
          chatbox.querySelector(".chatbox__messages").removeAttribute("lang");
        } else {
          this.args.langContainer.style.display = "none";
          this.args.inputField.style.display = "inline-block";
          this.args.sendButton.style.display = "inline-block";
        }
      })
      .catch((error) => {
        console.error("Error checking state:", error);
        this.messages.push({
          name: "Sam",
          message: "Error connecting to server. Please try again.",
        });
        this.updateChatText(chatbox);
      });
  }

  onLangButton(chatbox, lang) {
    fetch($SCRIPT_ROOT + "/select_language", {
      method: "POST",
      body: JSON.stringify({ language: lang }),
      mode: "cors",
      headers: { "Content-Type": "application/json" },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`);
        return r.json();
      })
      .then((r) => {
        this.args.langContainer.style.display = "none";
        this.args.inputField.style.display = "inline-block";
        this.args.sendButton.style.display = "inline-block";
        if (lang === "Arabic") {
          chatbox
            .querySelector(".chatbox__messages")
            .setAttribute("lang", "ar");
          this.args.inputField.setAttribute("dir", "rtl");
        } else {
          chatbox.querySelector(".chatbox__messages").removeAttribute("lang");
          this.args.inputField.removeAttribute("dir");
        }
        let msg = { name: "Sam", message: r.answer.replace(/\n/g, "<br>") };
        this.messages.push(msg);
        this.updateChatText(chatbox);
      })
      .catch((error) => {
        console.error("Error selecting language:", error);
        this.messages.push({
          name: "Sam",
          message:
            lang === "Arabic"
              ? "خطأ في الاتصال بالخادم. حاول مرة أخرى."
              : "Error connecting to server. Please try again.",
        });
        this.updateChatText(chatbox);
      });
  }

  onSendButton(chatbox) {
    const textField = this.args.inputField;
    let text1 = textField.value.trim();
    if (text1 === "") {
      return;
    }

    let msg1 = { name: "User", message: text1 };
    this.messages.push(msg1);
    this.updateChatText(chatbox);

    fetch($SCRIPT_ROOT + "/predict", {
      method: "POST",
      body: JSON.stringify({ message: text1 }),
      mode: "cors",
      headers: { "Content-Type": "application/json" },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`);
        return r.json();
      })
      .then((r) => {
        if (r.restart) {
          this.args.langContainer.style.display = "flex";
          this.args.inputField.style.display = "none";
          this.args.sendButton.style.display = "none";
          this.args.inputField.removeAttribute("dir");
          chatbox.querySelector(".chatbox__messages").removeAttribute("lang");
          this.messages = [];
          this.updateChatText(chatbox);
        } else {
          let msg2 = { name: "Sam", message: r.answer.replace(/\n/g, "<br>") };
          this.messages.push(msg2);
          if (r.continue_answer) {
            let msg3 = {
              name: "Sam",
              message: r.continue_answer.replace(/\n/g, "<br>"),
            };
            this.messages.push(msg3);
          }
          this.updateChatText(chatbox);
        }
        textField.value = "";
      })
      .catch((error) => {
        console.error("Error sending message:", error);
        const errorMsg =
          chatbox.querySelector(".chatbox__messages").getAttribute("lang") ===
          "ar"
            ? "خطأ في الاتصال بالخادم. حاول مرة أخرى."
            : "Error connecting to server. Please try again.";
        this.messages.push({ name: "Sam", message: errorMsg });
        this.updateChatText(chatbox);
        textField.value = "";
      });
  }

  updateChatText(chatbox) {
    let html = "";
    this.messages
      .slice()
      .reverse()
      .forEach(function (item) {
        if (item.name === "Sam") {
          html +=
            '<div class="messages__item messages__item--visitor">' +
            item.message +
            "</div>";
        } else {
          html +=
            '<div class="messages__item messages__item--operator">' +
            item.message +
            "</div>";
        }
      });

    const chatmessages = chatbox.querySelector(".chatbox__messages");
    chatmessages.innerHTML = html;
    chatmessages.scrollTop = chatmessages.scrollHeight;
  }
}

const chatbox = new Chatbox();
chatbox.display();
