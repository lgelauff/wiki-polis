/**
 * @license
 * Copyright (C) 2024 Guido Berhoerster <guido+particiapp@berhoerster.name>
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

/**
 * @document doc/pa-conversation.md
 * @document doc/pa-topic.md
 * @document doc/pa-description.md
 * @document doc/pa-statement.md
 * @document doc/pa-login-button.md
 * @document doc/pa-vote-button.md
 * @document doc/pa-submit-button.md
 * @document doc/pa-notifications-checkbox.md
 * @module particiapp-web-components
 */

import * as particiappWebClient from "@particiapp/particiapp-web-client";

/**
 * Minimum interval in ms for polling for new statements and results.
 * @type {number}
 */
const POLL_INTERVAL_MIN = 8000;
/**
 * Maximum interval in ms for polling for new statements and results.
 * @type {number}
 */
const POLL_INTERVAL_MAX = 12000;

/**
 * @param {any} value
 * @returns {Error}
 */
function ensureError(value) {
    return value instanceof Error ? value : new Error(String(value));
}

/**
 * The ParticiappElementConnectedEvent class representa a
 * particiappelementconnected event.  A particiappelementconnected event is
 * dispatched by a custom element from the Particiapp Web Components library
 * each time it is added to the document.
 */
export class ParticiappElementConnectedEvent extends Event {
    /**
     * The constructor returns a newly constructed
     * ParticiappElementConnectedEvent object.
     * @param {string} type - The name of the event.
     * @param {Object<string, any>} [options={}] - Optional values passed to
     *     the Event constructor.
     */
    constructor(type, options = {}) {
        super(type, { bubbles: true });
    }
}

/**
 * The ParticiappStateChangeEvent class represents a particiappstatechange
 * event.  A particiappstatechange event is dispatched by the
 * <pa-conversation> when its {@link ParticiappConversationElement.state}
 * property has changed.
 */
export class ParticiappStateChangeEvent extends Event {
    /**
     * The constructor returns a newly constructed ParticiappStateChangeEvent
     * object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {string} [options.state] - The value of the state property of the
     *     <pa-conversation>.
     */
    constructor(type, options = {}) {
        super(type);
        /** The value of the state property of the &lt;pa-conversation&gt;. */
        this.state = options.state;
    }
}

/**
 * The ParticiappAuthenticationChangeEvent class represents a
 * particiappauthenticationchange event.  A particiappauthenticationchange
 * event is dispatched by the <pa-conversation> when its authentication state
 * has changed.
 */
export class ParticiappAuthenticationChangeEvent extends Event {
    /**
     * The constructor returns a newly constructed
     * ParticiappAuthenticationChangeEvent object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {boolean} [options.authenticated] - Whether the client is
     *     authenticated.
     * @param {boolean} [options.authenticationRequired] - Whether the
     *     server requires authentication.
     */
    constructor(type, options = {}) {
        super(type);
        /** Whether the client is authenticated. */
        this.authenticated = options.authenticated;
        /** Whether the server requires authentication. */
        this.authenticationRequired = options.authenticationRequired;
    }
}

/**
 * The ParticiappConversationChangeEvent class represents a
 * particiappconversationchange event.  A particiappconversationchange event is
 * dispatched by the <pa-conversation> when the associated conversation has
 * changed.
 */
export class ParticiappConversationChangeEvent extends Event {
    /**
     * The constructor returns a newly constructed
     * ParticiappConversationChangeEvent object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {particiappWebClient.Conversation} [options.conversation] - The
     *     conversation associated with the &lt;pa-conversation&gt;.
     */
    constructor(type, options = {}) {
        super(type);
        /** The conversation associated with the &lt;pa-conversation&gt;. */
        this.conversation = options.conversation;
    }
}

/**
 * The ParticiappStatementsChangeEvent class represents a
 * particiappstatementschange event.  A particiappstatementschange event is
 * dispatched by the <pa-conversation> when the statements have changed.
 */
export class ParticiappStatementsChangeEvent extends Event {
    /**
     * The constructor returns a newly constructed
     * ParticiappStatementsChangeEvent object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {Map<number, particiappWebClient.Statement>} [options.statements] - The
     *     statements associated with the &lt;pa-conversation&gt;.
     */
    constructor(type, options = {}) {
        super(type);
        /** The statements associated with the &lt;pa-conversation&gt;. */
        this.statements = options.statements;
    }
}

/**
 * The ParticiappResultsChangeEvent class represents a particiappresultschange
 * event.  A particiappresultschange event is dispatched by the
 * <pa-conversation> when the voting results have changed.
 */
export class ParticiappResultsChangeEvent extends Event {
    /**
     * The constructor returns a newly constructed ParticiappResultsChangeEvent
     * object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {particiappWebClient.Results} [options.results] - The voting results
     *     associated with the &lt;pa-conversation&gt;.
     */
    constructor(type, options = {}) {
        super(type);
        /** The voting results associated with the &lt;pa-conversation&gt;. */
        this.results = options.results;
    }
}

/**
 * The ParticiappAuthenticationStartedEvent class represents a
 * particiappauthenticationstarted event.  A particiappauthenticationstarted
 * event is dispatched by the <pa-conversation> when the authentication
 * process has been started.
 */
export class ParticiappAuthenticationStartedEvent extends Event {
}

/**
 * The ParticiappAuthenticationSuccessEvent class represents a
 * particiappauthenticationsuccess event.  A particiappauthenticationsuccess
 * event is dispatched by the <pa-conversation> when the authentication
 * process was completed successfully.
 */
export class ParticiappAuthenticationSuccessEvent extends Event {
}

/**
 * The ParticiappAuthenticationErrorEvent class represents a
 * particiappauthenticationerror event.  A particiappauthenticationerror event
 * is dispatched by the <pa-conversation> when the authentication process has
 * failed due to an error.
 */
export class ParticiappAuthenticationErrorEvent extends Event {
    /**
     * The constructor returns a newly constructed
     * ParticiappAuthenticationErrorEvent object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {Error} [options.error] - The error that occurred during the
     *     authentication process.
     */
    constructor(type, options = {}) {
        super(type);
        /** The error that occurred during the authentication process. */
        this.error = options.error;
    }
}

/**
 * The ParticiappVoteSubmitSuccessEvent class represents a
 * particiappvotesubmitsuccess event.  A particiappvotesubmitsuccess event is
 * dispatched by the <pa-conversation> when a vote for a statement has been
 * submitted successfully.
 */
export class ParticiappVoteSubmitSuccessEvent extends Event {
    /**
     * The constructor returns a newly constructed
     * ParticiappVoteSubmitSuccessEvent object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {string} [options.statementID] - The statement identifier.
     * @param {string} [options.value] - The statement text.
     */
    constructor(type, options = {}) {
        super(type);
        /** The statement identifier. */
        this.statementID = options.statementID;
        /** The statement text. */
        this.value = options.value;
    }
}

/**
 * The ParticiappVoteSubmitErrorEvent class represents a
 * particiappvotesubmiterror event.  A particiappvotesubmiterror event is
 * dispatched by the <pa-conversation> when a vote for a statement could not
 * be submitted due to an error.
 */
export class ParticiappVoteSubmitErrorEvent extends Event {
    /**
     * The constructor returns a newly constructed
     * ParticiappVoteSubmitErrorEvent object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {Error} [options.error] - The error that occurred when submitting
     *     the vote.
     */
    constructor(type, options = {}) {
        super(type);
        /** The error that occurred when submitting the vote. */
        this.error = options.error;
    }
}

/**
 * The ParticiappStatementSubmitSuccessEvent class represents a
 * particiappstatementsubmitsuccess event.  A particiappstatementsubmitsuccess
 * event is dispatched by the <pa-conversation> when a statement has been
 * submitted successfully.
 */
export class ParticiappStatementSubmitSuccessEvent extends Event {
    /**
     * The constructor returns a newly constructed
     * ParticiappStatementSubmitSuccessEvent object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {string} [options.value] - The statement text.
     */
    constructor(type, options = {}) {
        super(type);
        /** The statement text. */
        this.value = options.value;
    }
}

/**
 * The ParticiappStatementSubmitErrorEvent class represents a
 * particiappstatementsubmiterror event.  A particiappstatementsubmiterror
 * event is dispatched by the <pa-conversation> when a statement could not be
 * submitted due to an error.
 */
export class ParticiappStatementSubmitErrorEvent extends Event {
    /**
     * The constructor returns a newly constructed
     * ParticiappStatementSubmitErrorEvent object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {Error} [options.error] - The error that occurred when submitting
     *     the statement.
     */
    constructor(type, options = {}) {
        super(type);
        /** The error that occurred when submitting the statement. */
        this.error = options.error;
    }
}

/**
 * The ParticiappNotificationsSubmitSuccessEvent class represents a
 * particiappnotificationssubmitsuccess event.  A
 * particiappnotificationssubmitsuccess event is dispatched by the
 * <pa-conversation> when notification preferences have been submitted
 * successfully.
 */
export class ParticiappNotificationsSubmitSuccessEvent extends Event {
    /**
     * The constructor returns a newly constructed
     * ParticiappNotificationsSubmitSuccessEvent object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {boolean} [options.value] - Whether notifications are enabled.
     */
    constructor(type, options = {}) {
        super(type);
        /** Whether notifications are enabled. */
        this.value = options.value;
    }
}

/**
 * The ParticiappNotificationsSubmitErrorEvent class represents a
 * particiappnotificationssubmiterror event.  A
 * particiappnotificationssubmiterror event is dispatched by the
 * <pa-conversation> when notification preferences could not be submitted due
 * to an error.
 */
export class ParticiappNotificationsSubmitErrorEvent extends Event {
    /**
     * The constructor returns a newly constructed
     * ParticiappNotificationsSubmitErrorEvent object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {Error} [options.error] - The error that occurred when submitting
     *     the notification preferences.
     */
    constructor(type, options = {}) {
        super(type);
        /**
         * The error that occurred when submitting the notification
         * preferences.
         */
        this.error = options.error;
    }
}

/**
 * The ParticiappAuthenticateEvent class represents a particiappauthenticate
 * event. A particiappauthenticate is dispatched by the <pa-login-button>
 * when the button was interacted with.
 */
export class ParticiappAuthenticateEvent extends Event {
    /**
     * The constructor returns a newly constructed ParticiappAuthenticateEvent
     * object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     */
    constructor(type, options = {}) {
        super(type, { bubbles: true });
    }
}

/**
 * The ParticiappVoteSubmitEvent class represents a particiappvotesubmit event.
 * A particiappvotesubmit is dispatched by the <pa-vote-button> when the
 * button was interacted with.
 */
export class ParticiappVoteSubmitEvent extends Event {
    /**
     * The constructor returns a newly constructed ParticiappVoteSubmitEvent
     * object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {string} [options.statementID] - The statement identifier.
     * @param {string} [options.value] - The vote value.
     */
    constructor(type, options = {}) {
        super(type, { bubbles: true });
        /** The statement identifier. */
        this.statementID = options.statementID;
        /** The vote value. */
        this.value = options.value;
    }
}

/**
 * The ParticiappStatementSubmitEvent class represents a
 * particiappstatementsubmit event. A particiappstatementsubmit is dispatched
 * by the <pa-submit-button> when statement submission was requested.
 */
export class ParticiappStatementSubmitEvent extends Event {
    /**
     * The constructor returns a newly constructed ParticiappStatementSubmitEvent object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {string} [options.value] - The statement text.
     * @param {Element} [options.inputElement] - The input element associated
     *     with the &lt;pa-submit-button&gt;.
     */
    constructor(type, options = {}) {
        super(type, { bubbles: true });
        /** The statement text. */
        this.value = options.value;
        /** The input element associated with the &lt;pa-submit-button&gt;. */
        this.inputElement = options.inputElement;
    }
}

/**
 * The ParticiappNotificationsSubmitEvent class represents a
 * particiappnotificationssubmit event. A particiappnotificationssubmit is
 * dispatched by the <pa-notifications-checkbox> when the checkbox input
 * element was interacted with.
 */
export class ParticiappNotificationsSubmitEvent extends Event {
    /**
     * The constructor returns a newly constructed
     * ParticiappNotificationsSubmitEvent object.
     * @param {string} type - The name of the event.
     * @param {Object} [options={}] - Optional values passed to
     *     the Event constructor.
     * @param {boolean} [options.value] - Whether notifications are enabled.
     */
    constructor(type, options = {}) {
        super(type, { bubbles: true });
        /** Whether notifications are enabled. */
        this.value = options.value;
    }
}

/**
 * The ParticiappConversationElement class represents a <pa-conversation>
 * element which provides methods and properties for interacting with a
 * conversation.
 */
export class ParticiappConversationElement extends HTMLElement {
    static observedAttributes = ["disabled"];
    /** @type {ElementInternals} */
    #internals;
    #childElements = [
        "pa-topic",
        "pa-description",
        "pa-statement",
        "pa-login-button",
        "pa-vote-button",
        "pa-submit-button",
        "pa-notifications-checkbox",
    ];
    #state = "loading";
    #error = "";
    /** @type {particiappWebClient.ConversationClient|undefined} */
    #client;
    /** @type {?Window} */
    #loginWindow = null;
    /** @type {?number} */
    #loginWindowTimer = null;
    /** @type {?number} */
    #pollTimer = null;
    /** @type {?particiappWebClient.Statement} */
    statement = null;

    /**
     * The constructor returns a newly constructed
     * ParticiappConversationElement object.
     */
    constructor() {
        super();

        const sheet = new CSSStyleSheet();
        sheet.replaceSync(`
            :host {
                display: block;
            }
            :host([hidden]) {
                display: none;
            }
        `);

        const shadow = this.attachShadow({ mode: "open" });
        shadow.adoptedStyleSheets = [sheet];
        shadow.appendChild(document.createElement("slot"));
        this.#internals = this.attachInternals();
        this.#updateInternalsStates();
    }

    /**
     * The #nonNullClient method assert the client has been initialized.
     * @returns {particiappWebClient.ConversationClient}
     */
    #nonNullClient() {
        if (typeof this.#client === "undefined" || this.#client === null) {
            throw new TypeError("client has not been initialized");
        }
        return this.#client;
    }

    #updateInternalsStates() {
        for (
            const state of [
                "loading",
                "loaded",
                "error",
                "inactive",
                "unauthenticated",
            ]
        ) {
            this.#internals.states.delete(state);
        }
        this.#internals.states.add(this.#state);
        if (!this.#client?.conversation.isActive) {
            this.#internals.states.add("inactive");
        } else if (this.#client?.authenticationRequired) {
            this.#internals.states.add("unauthenticated");
        }
    }

    /**
     * @param {string} state
     */
    #setState(state) {
        if (state === this.#state) {
            return;
        }
        this.#state = state;
        this.#updateChildElements(
            ...this.querySelectorAll(this.#childElements.join(",")),
        );
        this.dispatchEvent(
            new ParticiappStateChangeEvent("particiappstatechange", { state }),
        );
    }

    async #init() {
        if (typeof this.#client === "undefined") {
            const base = this.getAttribute("base");
            const conversationID = this.getAttribute("conversation-id");
            if (!base || !conversationID) {
                const message = !base ? "missing base attribute" : "missing conversation-id attribute";
                this.#error = message;
                this.#setState("error");
                this.#updateInternalsStates();
                console.error("Failed to load conversation:", message);
                return;
            }
            this.#client = new particiappWebClient.ConversationClient(
                base,
                conversationID,
            );
        }

        const oldAuthenticationRequired = this.#client.authenticationRequired;
        const oldIsActive = this.#client.conversation.isActive;
        try {
            await this.#client.init();
        } catch (e) {
            this.#error = ensureError(e).message;
            this.#setState("error");
            this.#updateInternalsStates();
            console.error("Failed to load conversation:", e);
            return;
        }

        this.statement = this.#client.currentStatement() ?? null;

        if (this.#state === "loading") {
            this.addEventListener("particiappelementconnected", this);
            this.addEventListener("particiappvotesubmit", this);
            this.addEventListener("particiappstatementsubmit", this);
            this.addEventListener("particiappauthenticate", this);
            this.addEventListener("particiappnotificationssubmit", this);
            window.addEventListener("message", this);

            this.#setState("loaded");
            this.#updateInternalsStates();
        } else if (
            this.#client.authenticationRequired !== oldAuthenticationRequired ||
            this.#client.conversation.isActive !== oldIsActive
        ) {
            this.#updateInternalsStates();
            this.#updateChildElements(
                ...this.querySelectorAll(this.#childElements.join(",")),
            );
        } else {
            this.#updateChildElements(
                ...this.querySelectorAll(this.#childElements.join(",")),
            );
        }

        if (
            this.#client.conversation.isActive &&
            !this.#client.authenticationRequired
        ) {
            this.#startPoll();
        }

        console.debug(`Conversation ${this.#client.conversationID} loaded`);
    }

    connectedCallback() {
        // initialize client here since it requires access to attributes
        if (typeof this.#client === "undefined") {
            const base = this.getAttribute("base");
            const conversationID = this.getAttribute("conversation-id");
            if (!base || !conversationID) {
                const message = !base ? "missing base attribute" : "missing conversation-id attribute";
                this.#error = message;
                this.#setState("error");
                this.#updateInternalsStates();
                console.error("Failed to load conversation:", message);
                return;
            }
            this.#client = new particiappWebClient.ConversationClient(
                base,
                conversationID,
            );
            this.#init();
        }
    }

    /**
     * @param {string} name
     * @param {string} oldValue
     * @param {string} newValue
     */
    attributeChangedCallback(name, oldValue, newValue) {
        console.debug(
            `Attribute ${name} has changed from ${oldValue} to ${newValue}`,
        );
        switch (name) {
            case "disabled":
                // disabling this element also disables child elements
                for (
                    const element of /** @type {NodeListOf<ParticiappButtonElement>} */(this.querySelectorAll(
                        "pa-vote-button,pa-vote-button,pa-login-button",
                    ))
                ) {
                    if (element.disabled !== this.disabled) {
                        element.disabled = this.disabled;
                    }
                }
                break;
        }
    }

    /**
     * @param {Event} ev
     */
    handleEvent(ev) {
        console.debug("Event:", ev);

        if (this.state === "error") {
            return;
        }

        let evt;
        switch (ev.type) {
            case "particiappelementconnected":
                evt = /** @type {ParticiappElementConnectedEvent} */(ev);
                if (evt.target instanceof Element) {
                    this.#updateChildElements(evt.target);
                }
                break;
            case "particiappauthenticate":
                this.startAuthentication();
                break;
            case "particiappvotesubmit":
                evt = /** @type {ParticiappVoteSubmitEvent} */(ev);
                if (typeof evt.value !== "undefined") {
                    this.submitVote(evt.value, evt.statementID);
                }
                break;
            case "particiappstatementsubmit":
                evt = /** @type {ParticiappStatementSubmitEvent} */(ev);
                if (typeof evt.value !== "undefined") {
                    this.#submitStatement(evt.value, evt.inputElement);
                }
                break;
            case "particiappnotificationssubmit":
                evt = /** @type {ParticiappNotificationsSubmitEvent} */(ev);
                if (typeof evt.value !== "undefined") {
                    this.submitNotifications(evt.value);
                }
                break;
            case "message":
                evt = /** @type {MessageEvent} */(ev);
                this.#onMessage(evt);
                break;
            default:
                console.warn("Unhandled event:", ev);
        }
    }

    /**
     * Reflects the value of the baseurl HTML attribute.
     */
    get baseURL() {
        return this.#nonNullClient().baseURL;
    }

    /**
     * Reflects the value of the conversationid HTML attribute.
     */
    get conversationID() {
        return this.#nonNullClient().conversationID;
    }

    /**
     * Reflects the value of the disabled HTML attribute.
     */
    get disabled() {
        return this.hasAttribute("disabled");
    }

    /**
     * @param {any} value
     */
    set disabled(value) {
        this.toggleAttribute("disabled", Boolean(value));
    }

    /**
     * Describes the state of the conversation.
     */
    get state() {
        return this.#state;
    }

    /**
     * Describes a fatal error that occured when interacting with the server.
     */
    get error() {
        return this.#error;
    }

    /**
     * Returns the conversation client object.
     */
    get client() {
        return this.#client;
    }

    /**
     * @param  {...Element} elements
     */
    #updateChildElements(...elements) {
        for (const element of elements) {
            if (element instanceof ParticiappTopicElement) {
                element.text = this.#nonNullClient().conversation.topic;
            } else if (element instanceof ParticiappDescriptionElement) {
                const descriptionDocument = this.#nonNullClient().conversation.descriptionDocument;
                if (descriptionDocument) {
                    element.contentElement.replaceChildren(descriptionDocument);
                } else {
                    element.text = this.#nonNullClient().conversation.description;
                }
            } else if (element instanceof ParticiappStatementElement) {
                if (this.statement !== null) {
                    element.text = this.statement.text
                    element.noStatement = false;
                } else {
                    element.text = "";
                    element.noStatement = true;
                }
            } else if (element instanceof ParticiappLoginButtonElement) {
                element.inactive = !this.#nonNullClient().authenticationRequired ||
                    this.#loginWindow !== null;
            } else if (element instanceof ParticiappVoteButtonElement) {
                element.inactive = this.state !== "loaded" ||
                    this.statement === null ||
                    !this.#nonNullClient().conversation.isActive ||
                    this.#nonNullClient().authenticationRequired;
            } else if (element instanceof ParticiappSubmitButtonElement) {
                element.inactive = this.state !== "loaded" ||
                    !this.#nonNullClient().conversation.isActive ||
                    !this.#nonNullClient().conversation.statementsAllowed ||
                    this.#nonNullClient().authenticationRequired;
            } else if (element instanceof ParticiappNotificationsCheckboxElement) {
                element.inactive = this.state !== "loaded" ||
                    !this.#nonNullClient().conversation.isActive ||
                    !this.#nonNullClient().conversation.notificationsAvailable ||
                    !this.#nonNullClient().authenticated;
                element.value =
                    this.#nonNullClient().participant.notifications.enabled;
            } else {
                console.error("failed to update unknown element:", element)
            }
        }
    }

    /**
     * The startAuthentication method starts the authentication process by
     * opening a popup window which redirects the user to the OpenID Connect
     * identity provider.
     */
    startAuthentication() {
        if (this.#loginWindow !== null) {
            return;
        }

        const width = 600;
        const height = 600;
        const left = Math.max(window.screen.width - width, 0) / 2;
        const top = Math.max(window.screen.height - height, 0) / 2;
        this.#loginWindow = window.open(
            this.#nonNullClient().loginURL,
            "pa-login",
            `popup width=${width} height=${height} top=${top} left=${left}`,
        );
        if (this.#loginWindow === null) {
            return;
        }

        // check if window has been closed without successful authentication
        this.#loginWindowTimer = setInterval(
            this.#onLoginWindowTimer.bind(this),
            1000,
        );

        this.#updateChildElements(
            ...this.querySelectorAll("pa-login-button"),
        );

        this.dispatchEvent(
            new ParticiappAuthenticationStartedEvent(
                "particiappauthenticationstarted",
            ),
        );
    }

    /**
     * @param {MessageEvent} ev
     */
    async #onMessage(ev) {
        if (
            this.#loginWindow === null ||
            ev.origin !== this.#nonNullClient().baseURL.origin
        ) {
            return;
        }

        clearInterval(this.#loginWindowTimer ?? undefined);
        this.#loginWindowTimer = null;
        this.#loginWindow.close();
        this.#loginWindow = null;

        if (typeof ev.data === "string" && ev.data !== "") {
            const error = new Error(
                `Unexpected message "${ev.data}" from login window`,
            );
            this.dispatchEvent(
                new ParticiappAuthenticationErrorEvent(
                    "particiappauthenticationerror",
                    { error },
                ),
            );
            console.error(error.message);
            return;
        }

        // reinitialize the client
        await this.#init();
        this.dispatchEvent(
            new ParticiappAuthenticationSuccessEvent(
                "particiappauthenticationsuccess",
            ),
        );
    }

    #onLoginWindowTimer() {
        if (this.#loginWindow === null || this.#loginWindow.closed) {
            clearInterval(this.#loginWindowTimer ?? undefined);

            this.#loginWindowTimer = null;
            this.#loginWindow = null;

            this.#updateChildElements(
                ...this.querySelectorAll("pa-login-button"),
            );

            const error = new Error("Authentication process cancelled by user");
            this.dispatchEvent(
                new ParticiappAuthenticationErrorEvent(
                    "particiappauthenticationerror",
                    { error },
                ),
            );
            console.debug(error.message);
        }
    }

    /**
     * @param {Error} error
     */
    #handleCommonRequestErrors(error) {
        if (error instanceof particiappWebClient.AuthenticationRequiredError) {
            this.#stopPoll();
            this.#updateInternalsStates();
            this.#updateChildElements(
                ...this.querySelectorAll(this.#childElements.join(",")),
            );
            this.dispatchEvent(
                new ParticiappAuthenticationChangeEvent(
                    "particiappauthenticationchange",
                    {
                        authenticated: this.#nonNullClient().authenticated,
                        authenticationRequired:
                            this.#nonNullClient().authenticationRequired,
                    },
                ),
            );
        } else if (error instanceof particiappWebClient.ConversationInactiveError) {
            this.#stopPoll();
            this.#updateInternalsStates();
            this.#updateChildElements(
                ...this.querySelectorAll(this.#childElements.join(",")),
            );
            this.dispatchEvent(
                new ParticiappConversationChangeEvent(
                    "particiappconversationchange",
                    { conversation: this.#nonNullClient().conversation },
                ),
            );
        }
    }

    /**
     * The submitVote method submits a vote for a statement.
     * @param {string} value - Value representing the vote.
     * @param {?string} [statementID=null] - The statement identifier of the
     *     statement voted on or null for the current statement.
     */
    async submitVote(value, statementID = null) {
        // statement ID is optional, fall back to the current statement
        statementID = statementID ?? this.statement?.id.toString();
        if (typeof statementID === "undefined") {
            return;
        }

        let vote;
        switch (value) {
            case "agree":
                vote = particiappWebClient.Vote.Agree;
                break;
            case "disagree":
                vote = particiappWebClient.Vote.Disagree;
                break;
            case "neutral":
                vote = particiappWebClient.Vote.Neutral;
                break;
            default:
                throw new TypeError("Received invalid vote value.");
                return;
        }

        try {
            await this.#nonNullClient().addVote(statementID, vote);
        } catch (e) {
            const error = ensureError(e);
            this.dispatchEvent(
                new ParticiappVoteSubmitErrorEvent(
                    "particiappvotesubmiterror",
                    { error },
                ),
            );
            this.#handleCommonRequestErrors(error);
            console.error("Failed to submit vote:", e);
            return;
        }

        this.statement = this.#nonNullClient().currentStatement() ?? null;
        this.#updateChildElements(
            ...this.querySelectorAll("pa-statement,pa-vote-button"),
        );
        this.dispatchEvent(
            new ParticiappVoteSubmitSuccessEvent(
                "particiappvotesubmitsuccess",
                { statementID, value },
            ),
        );
    }

    /**
     * @param {string} value
     * @param {Element=} inputElement
     */
    async #submitStatement(value, inputElement) {
        if (typeof value === "undefined") {
            throw new TypeError("The statement value is missing.");
        }

        value = value.trim();

        try {
            await this.#nonNullClient().addStatement(value);
        } catch (e) {
            if (e instanceof particiappWebClient.StatementsNotAllowedError) {
                this.#updateChildElements(
                    ...this.querySelectorAll("pa-submit-button"),
                );
                this.dispatchEvent(
                    new ParticiappStatementSubmitErrorEvent(
                        "particiappstatementsubmiterror",
                        { error: e },
                    ),
                );
                this.dispatchEvent(
                    new ParticiappConversationChangeEvent(
                        "particiappconversationchange",
                        { conversation: this.#nonNullClient().conversation },
                    ),
                );
                console.debug(e.message);
            } else {
                const error = ensureError(e);
                this.dispatchEvent(
                    new ParticiappStatementSubmitErrorEvent(
                        "particiappstatementsubmiterror",
                        { error },
                    ),
                );
                this.#handleCommonRequestErrors(error);
                console.error("Failed to submit statement:", error);
            }
            return;
        }

        if (typeof inputElement !== "undefined" && "value" in inputElement) {
            inputElement.value = "";
        }
        this.dispatchEvent(
            new ParticiappStatementSubmitSuccessEvent(
                "particiappstatementsubmitsuccess",
                { value },
            ),
        );
    }

    /**
     * The submitStatement method submits a new statement.
     * @param {string} value - The statement text.
     * @returns {Promise<void>}
     */
    async submitStatement(value) {
        return this.#submitStatement(value);
    }

    /**
     * The submitNotifications method submits notifications preferences.
     * @param {boolean} value - Whether notifications are enabled.
     * @returns {Promise<void>}
     */
    async submitNotifications(value) {
        if (typeof value === "undefined") {
            throw new TypeError("The value is missing.");
        }

        try {
            await this.#nonNullClient().setNotifications(value);
        } catch (e) {
            if (
                (e instanceof particiappWebClient.NotificationsNotAvailableError) ||
                (e instanceof particiappWebClient.EmailAddressMissingError)
            ) {
                this.#updateChildElements(
                    ...this.querySelectorAll("pa-notifications-checkbox"),
                );
                this.dispatchEvent(
                    new ParticiappNotificationsSubmitErrorEvent(
                        "particiappnotificationssubmiterror",
                        { error: e },
                    ),
                );
                this.dispatchEvent(
                    new ParticiappConversationChangeEvent(
                        "particiappconversationchange",
                        { conversation: this.#nonNullClient().conversation },
                    ),
                );
                console.debug(e.message);
            } else {
                const error = ensureError(e);
                this.dispatchEvent(
                    new ParticiappNotificationsSubmitErrorEvent(
                        "particiappnotificationssubmiterror",
                        { error },
                    ),
                );
                this.#handleCommonRequestErrors(error);
                console.error(
                    "Failed to submit notifications subscription:",
                    error,
                );
            }
            return;
        }

        this.dispatchEvent(
            new ParticiappNotificationsSubmitSuccessEvent(
                "particiappnotificationssubmitsuccess",
                { value },
            ),
        );
    }

    async #onPollTimer() {
        this.#pollTimer = null;

        const [statementsResult, resultsResult] = await Promise.allSettled([
            this.#nonNullClient().pollStatements(),
            this.#nonNullClient().pollResults(),
        ]);
        const statementsChanged = statementsResult.status === "fulfilled" ? statementsResult.value : false;
        let resultsChanged = resultsResult.status === "fulfilled" ? resultsResult.value : false;
        if (
            (
                resultsResult.status === "rejected" &&
                resultsResult.reason instanceof particiappWebClient.AuthenticationRequiredError
            ) ||
            (
                statementsResult.status === "rejected" &&
                statementsResult.reason instanceof particiappWebClient.AuthenticationRequiredError
            )
        ) {
            this.#updateChildElements(
                ...this.querySelectorAll(this.#childElements.join(",")),
            );
            this.dispatchEvent(
                new ParticiappAuthenticationChangeEvent(
                    "particiappauthenticationchange",
                    {
                        authenticated: this.#nonNullClient().authenticated,
                        authenticationRequired:
                            this.#nonNullClient().authenticationRequired,
                    },
                ),
            );
        } else if (
            resultsResult.status === "rejected" &&
            resultsResult.reason instanceof particiappWebClient.ResultsNotAvailableError
        ) {
            resultsChanged = true;
        } else {
            if (resultsResult.status === "rejected") {
                console.error("Failed to poll results:", resultsResult.reason);
            }
            if (statementsResult.status === "rejected") {
                console.error("Failed to poll statements:", statementsResult.reason);
            }
        }

        if (
            this.#nonNullClient().conversation.isActive &&
            !this.#nonNullClient().authenticationRequired
        ) {
            this.#startPoll();
        }

        if (statementsChanged) {
            if (this.statement === null) {
                // all statements had already been voted on, update the current statement
                this.statement = this.#nonNullClient().currentStatement() ?? null;
                this.#updateChildElements(
                    ...this.querySelectorAll("pa-statement,pa-vote-button"),
                );
            }
            this.dispatchEvent(
                new ParticiappStatementsChangeEvent(
                    "particiappstatementschange",
                    { statements: this.#nonNullClient().statements },
                ),
            );
        }
        if (resultsChanged) {
            this.dispatchEvent(
                new ParticiappResultsChangeEvent("particiappresultschange", {
                    results: this.#nonNullClient().results,
                }),
            );
        }
    }

    #startPoll() {
        if (this.#pollTimer !== null) {
            return;
        }
        const minCeiled = Math.ceil(POLL_INTERVAL_MIN);
        const maxFloored = Math.floor(POLL_INTERVAL_MAX);
        const interval = Math.floor(
            Math.random() * (maxFloored - minCeiled) + minCeiled,
        );
        this.#pollTimer = setTimeout(this.#onPollTimer.bind(this), interval);
    }

    #stopPoll() {
        if (this.#pollTimer === null) {
            return;
        }
        clearTimeout(this.#pollTimer);
        this.#pollTimer = null;
    }
}

/**
 * The ParticiappContentElement represents an abstract custom element for
 * displaying text content.
 */
export class ParticiappContentElement extends HTMLElement {
    contentElement;

    /**
     * The constructor returns a newly constructed ParticiappContentElement
     * object.
     */
    constructor() {
        super();

        const sheet = new CSSStyleSheet();
        sheet.replaceSync(`
            :host {
                display: inline;
            }
            :host([hidden]) {
                display: none;
            }
        `);

        const shadow = this.attachShadow({ mode: "open" });
        shadow.adoptedStyleSheets = [sheet];
        this.contentElement = document.createElement("span");
        this.contentElement.id = "content";
        shadow.appendChild(this.contentElement);
    }

    connectedCallback() {
        customElements.whenDefined("pa-conversation").then(() => {
            this.dispatchEvent(
                new ParticiappElementConnectedEvent(
                    "particiappelementconnected",
                ),
            );
        });
    }

    /**
     * The text content of the element.
     */
    get text() {
        return this.contentElement.textContent;
    }

    /**
     * @param {?string} value
     */
    set text(value) {
        this.contentElement.textContent = value;
    }
}

/**
 * The ParticiappTopicElement class represents an <pa-topic> element which
 * displays the conversation topic.
 */
export class ParticiappTopicElement extends ParticiappContentElement {}

/**
 * The ParticiappDescriptionElement class represents an <pa-description> element which
 * displays the conversation description.
 */
export class ParticiappDescriptionElement extends ParticiappContentElement {}

/**
 * The ParticiappStatementElement class represents an <pa-statement> element which
 * displays the text of the current statement.
 */
export class ParticiappStatementElement extends ParticiappContentElement {
    #internals;

    /**
     * The constructor returns a newly constructed ParticiappContentElement
     * object.
     */
    constructor() {
        super();

        const sheet = new CSSStyleSheet();
        sheet.replaceSync(`
            #no-statement {
                display: none;
            }

            :host(:state(no-statement)) #no-statement {
                display: inherit;
            }
        `);

        const noStatementElement = document.createElement("span");
        noStatementElement.id = "no-statement";
        noStatementElement.appendChild(document.createElement("slot"));
        if (typeof this.shadowRoot === "undefined" || this.shadowRoot === null) {
            throw new TypeError("shadow root has not been attached");
        }
        this.shadowRoot.appendChild(noStatementElement);
        this.shadowRoot.adoptedStyleSheets.push(sheet);
        this.#internals = this.attachInternals();
        this.#internals.states.add("no-statement");
    }

    get noStatement() {
        return this.#internals.states.has("no-statement");
    }

    /**
     * @param {any} value
     */
    set noStatement(value) {
        if (value) {
            this.#internals.states.add("no-statement");
        } else {
            this.#internals.states.delete("no-statement");
        }
    }
}

/**
 * The ParticiappButtonElement represents an abstract custom button element.
 */
export class ParticiappButtonElement extends HTMLElement {
    static observedAttributes = ["disabled"];
    #internals;
    #inactive = true;
    #buttonElement;

    /**
     * The constructor returns a newly constructed ParticiappButtonElement
     * object.
     */
    constructor() {
        super();

        const sheet = new CSSStyleSheet();
        sheet.replaceSync(`
            :host {
                display: inline;
            }
            :host([hidden]) {
                display: none;
            }
        `);
        this.#buttonElement = document.createElement("button");
        this.#buttonElement.part.add("button");
        this.#buttonElement.appendChild(document.createElement("slot"));
        const shadow = this.attachShadow({ mode: "open" });
        shadow.adoptedStyleSheets = [sheet];
        shadow.appendChild(this.#buttonElement);
        this.#internals = this.attachInternals();
        this.addEventListener("click", this);
    }

    connectedCallback() {
        customElements.whenDefined("pa-conversation").then(() => {
            this.dispatchEvent(
                new ParticiappElementConnectedEvent(
                    "particiappelementconnected",
                ),
            );
        });
    }

    /**
     * @param {string} name
     * @param {string} oldValue
     * @param {string} newValue
     */
    attributeChangedCallback(name, oldValue, newValue) {
        console.debug(
            `Attribute ${name} has changed from ${oldValue} to ${newValue}`,
        );
        switch (name) {
            case "disabled":
                this.#buttonElement.disabled = this.disabled;
                break;
        }
    }

    /**
     * @param {Event} ev
     */
    handleEvent(ev) {
    }

    /**
     * Reflects the disabled HTML attribute of the element.
     */
    get disabled() {
        return this.hasAttribute("disabled");
    }

    /**
     * @param {any} value
     */
    set disabled(value) {
        this.toggleAttribute("disabled", Boolean(value));
    }

    /**
     * Reflects the inactive custom state.
     */
    get inactive() {
        return this.#inactive;
    }

    /**
     * @param {any} value
     */
    set inactive(value) {
        this.#inactive = value;
        this.#buttonElement.disabled = value || this.disabled;
        if (value) {
            this.#internals.states.add("inactive");
        } else {
            this.#internals.states.delete("inactive");
        }
    }
}

/**
 * The ParticiappLoginButtonElement class represents an <pa-login-button>
 * element which provides a button for starting the authentication process.
 */
export class ParticiappLoginButtonElement extends ParticiappButtonElement {
    /**
     * @param {Event} ev
     * @override
     */
    handleEvent(ev) {
        switch (ev.type) {
            case "click":
                this.dispatchEvent(
                    new ParticiappAuthenticateEvent("particiappauthenticate"),
                );
                break;
        }
    }
}

/**
 * The ParticiappVoteButtonElement class represents an <pa-vote-button> element
 * which provides a button for voting for the current statement.
 */
export class ParticiappVoteButtonElement extends ParticiappButtonElement {
    /** @override */
    static observedAttributes = [...super.observedAttributes, "type"];
    #type = "neutral";

    /**
     * @param {string} name
     * @param {string} oldValue
     * @param {string} newValue
     * @override
     */
    attributeChangedCallback(name, oldValue, newValue) {
        console.debug(
            `Attribute ${name} has changed from ${oldValue} to ${newValue}`,
        );
        switch (name) {
            case "type":
                this.type = newValue;
                return;
        }
        super.attributeChangedCallback(name, oldValue, newValue);
    }

    /**
     * @param {Event} ev
     * @override
     */
    handleEvent(ev) {
        switch (ev.type) {
            case "click":
                this.dispatchEvent(
                    new ParticiappVoteSubmitEvent("particiappvotesubmit", {
                        value: this.#type,
                    }),
                );
                break;
        }
    }

    /**
     * Reflects the value of the type HTML attribute.
     */
    get type() {
        return this.#type;
    }

    /**
     * @param {any} value
     */
    set type(value) {
        if (this.#type === value || !this.#isTypeValid(value)) {
            return;
        }
        this.#type = value;

        if (this.getAttribute("type") === value) {
            return;
        }
        this.setAttribute("type", value);
    }

    /**
     * @param {string} type
     * @returns {boolean}
     */
    #isTypeValid(type) {
        switch (type) {
            case "agree":
            case "disagree":
            case "neutral":
                return true;
        }
        return false;
    }
}

/**
 * The ParticiappSubmitButtonElement class represents an <pa-submit-button> element
 * which provides a button for submitting a statement.
 */
export class ParticiappSubmitButtonElement extends ParticiappButtonElement {
    /**
     *
     * @param {Event} ev
     * @override
     */
    handleEvent(ev) {
        switch (ev.type) {
            case "click":
                if (this.control === null) {
                    return;
                }
                const element = /** @type {HTMLInputElement|HTMLTextAreaElement} */(this.control);
                this.dispatchEvent(
                    new ParticiappStatementSubmitEvent(
                        "particiappstatementsubmit",
                        {
                            "value": element.value,
                            inputElement: element,
                        },
                    ),
                );
                break;
        }
    }

    /**
     * Reflects the value of the submitfor HTML attribute.
     */
    get submitFor() {
        return this.getAttribute("submitfor") ?? "";
    }

    /**
     * @type {string}
     */
    set submitFor(value) {
        this.setAttribute("submitfor", value);
    }

    /**
     * A reference to the input element with which the <pa-submit-button> is
     * associated or null if there is not associated element.
     */
    get control() {
        const id = this.getAttribute("submitfor");
        if (id === null) {
            return null;
        }
        const element = document.getElementById(id);
        if (!(element instanceof HTMLInputElement) && !(element instanceof HTMLTextAreaElement)) {
            return null;
        }
        return element;
    }

    /**
     * @type {HTMLElement|null}
     */
    set control(value) {
        if (!(value instanceof HTMLInputElement) && !(value instanceof HTMLTextAreaElement)) {
            return;
        }
        if (value.id === "") {
            return;
        }
        if (!("value" in value)) {
            return;
        }
        this.setAttribute("submitfor", value.id);
    }
}

/**
 * The ParticiappNotificationsCheckboxElement class represents an
 * <pa-notifications-checkbox> element which provides a checkbox input for
 * enabling or disabling notifications.
 */
export class ParticiappNotificationsCheckboxElement extends HTMLElement {
    static observedAttributes = ["disabled"];
    static formAssociated = true;
    #checkboxElement;
    #internals;
    #inactive = true;

    /**
     * The constructor returns a newly constructed
     * ParticiappNotificationsCheckboxElement object.
     */
    constructor() {
        super();

        const sheet = new CSSStyleSheet();
        sheet.replaceSync(`
            :host {
                display: inline;
            }
            :host([hidden]) {
                display: none;
            }
        `);
        this.#checkboxElement = document.createElement("input");
        this.#checkboxElement.type = "checkbox";
        this.#checkboxElement.part.add("checkbox");
        // click is handled outside the shadow root to allow for label support
        this.#checkboxElement.addEventListener(
            "click",
            (ev) => ev.preventDefault(),
        );
        const shadow = this.attachShadow({ mode: "open" });
        shadow.adoptedStyleSheets = [sheet];
        shadow.appendChild(this.#checkboxElement);
        this.#internals = this.attachInternals();
        this.addEventListener("click", this);
    }

    connectedCallback() {
        customElements.whenDefined("pa-conversation").then(() => {
            this.dispatchEvent(
                new ParticiappElementConnectedEvent(
                    "particiappelementconnected",
                ),
            );
        });
    }

    /**
     * @param {string} name
     * @param {string} oldValue
     * @param {string} newValue
     */
    attributeChangedCallback(name, oldValue, newValue) {
        console.debug(
            `Attribute ${name} has changed from ${oldValue} to ${newValue}`,
        );
        switch (name) {
            case "disabled":
                this.#checkboxElement.disabled = this.disabled;
                break;
        }
    }

    /**
     * @param {Event} ev
     */
    handleEvent(ev) {
        switch (ev.type) {
            case "click":
                this.dispatchEvent(
                    new ParticiappNotificationsSubmitEvent(
                        "particiappnotificationssubmit",
                        {
                            value: this.#checkboxElement.checked,
                        },
                    ),
                );
                break;
        }
    }

    /**
     * Reflects the value of the disabled HTML attribute.
     */
    get disabled() {
        return this.hasAttribute("disabled");
    }

    /**
     * @param {any} value
     */
    set disabled(value) {
        this.toggleAttribute("disabled", Boolean(value));
    }

    /**
     * Reflects the inactive custom state.
     */
    get inactive() {
        return this.#inactive;
    }

    /**
     * @param {any} value
     */
    set inactive(value) {
        this.#inactive = value;
        this.#checkboxElement.disabled = value || this.disabled;
        this.#checkboxElement.indeterminate = value;
        if (value) {
            this.#internals.states.add("inactive");
        } else {
            this.#internals.states.delete("inactive");
        }
    }

    /**
     * Whether the checkbox is checked.
     */
    get value() {
        return this.#checkboxElement.checked;
    }

    /**
     * @param {any} value
     */
    set value(value) {
        this.#checkboxElement.checked = value;
    }
}

window.customElements.define("pa-topic", ParticiappTopicElement);
window.customElements.define("pa-description", ParticiappDescriptionElement);
window.customElements.define("pa-statement", ParticiappStatementElement);
window.customElements.define("pa-login-button", ParticiappLoginButtonElement);
window.customElements.define("pa-vote-button", ParticiappVoteButtonElement);
window.customElements.define("pa-submit-button", ParticiappSubmitButtonElement);
window.customElements.define(
    "pa-notifications-checkbox",
    ParticiappNotificationsCheckboxElement,
);
window.customElements.define("pa-conversation", ParticiappConversationElement);
