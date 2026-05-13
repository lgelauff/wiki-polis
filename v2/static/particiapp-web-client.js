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
 * @module particiapp-web-client
 */

/**
 * @typedef {Object} APIProblemDetails - The APIProblemDetails type represents
 *     a Problem Details JSON Object (RFC 9457) returned by the Particiapi
 *     server.
 * @property {string} [type]
 * @property {string} [title]
 * @property {string} [detail]
 */

/**
 * @typedef {Object} APIStatement - Represents a statement JSON Object returned
 *     by the Particiapi server.
 * @property {string} text
 * @property {number} id
 * @property {boolean} is_meta
 * @property {boolean} is_seed
 */

/**
 * @typedef {Object} APIResult - The APIResult type represents a result JSON
 *     Object returned by the Particiapi server.
 * @property {number} statement_id
 * @property {string} statement_text
 * @property {number} value
 */

/**
 * @typedef {Object} APIGroupResults - The APIGroupResults type represents a
 *     group results JSON Object returned by the Particiapi server.
 * @property {APIResult[]} [agree]
 * @property {APIResult[]} [disagree]
 */

/**
 * @typedef {Object} APIResults - The APIResults type represents a results JSON
 *     Object returned by the Particiapi server.
 * @property {APIGroupResults} [majority]
 * @property {APIGroupResults[]} [groups]
 */

/**
 * @typedef {Object} APINotifications - The APINotifications type represents a
 *     notifications JSON Object returned by the Particiapi server.
 * @property {boolean} [notification.enabled]
 * @property {?string} [notification.email]
 */

/**
 * @typedef {Object} APIParticipant - The APIParticipant type represents a
 *     participant JSON Object returned by the Particiapi server.
 * @property {number[]} [participant.votes=[]]
 * @property {number[]} [participant.statements=[]]
 * @property {APINotifications} [participant.notifications={}]
 */

/**
 * @typedef {Object} APIConversation - The APIConversation type represents a
 *     conversation JSON Object returned by the Particiapi server.
 * @property {string} [conversation.topic]
 * @property {string} [conversation.description]
 * @property {string} [conversation.description_html]
 * @property {boolean} [conversation.is_active]
 * @property {boolean} [conversation.statements_allowed]
 * @property {boolean} [conversation.notifications_available]
 * @property {boolean} [conversation.results_available]
 * @property {Object.<number, APIStatement>} [conversation.seed_statements]
 */

/**
 * The ParticiapiError class is a base class all other errors in this module
 * inherit from.
 * @extends Error
 */
export class ParticiapiError extends Error {
    /**
     * The constructor returns a newly created ParticiapiError object.
     * @param {string} [message] - A human-readable description of the error.
     */
    constructor(message = "Unknown error") {
        super(message);
    }
}

/**
 * The NotFoundError class represents an error when a conversation could not be
 * found.
 * @extends ParticiapiError
 */
export class NotFoundError extends ParticiapiError {
    /**
     * he constructor returns a newly created NotFoundError object.
     * @param {string} [message] - A human-readable description of the error.
     */
    constructor(message = "Conversation was not found") {
        super(message);
    }
}

/**
 * The StatementExistsError class represents an error when a submitted
 * statement already exists.
 * @extends ParticiapiError
 */
export class StatementExistsError extends ParticiapiError {
    /**
     * The constructor returns a newly created StatementExistsError object.
     * @param {string} [message] - A human-readable description of the error.
     */
    constructor(message = "Statement already exists") {
        super(message);
    }
}

/**
 * The ConversationInactiveError class represents an error when a request is
 * submitted to an inactive conversation.
 * @extends ParticiapiError
 */
export class ConversationInactiveError extends ParticiapiError {
    /**
     * The constructor returns a newly created ConversationInactiveError
     * object.
     * @param {string} [message] - A human-readable description of the error.
     */
    constructor(message = "Conversation is inactive") {
        super(message);
    }
}

/**
 * The StatementsNotAllowedError class represents an error when submitting
 * statements is not allowed.
 * @extends ParticiapiError
 */
export class StatementsNotAllowedError extends ParticiapiError {
    /**
     * The constructor returns a newly created StatementsNotAllowedError
     * object.
     * @param {string} [message] - A human-readable description of the error.
     */
    constructor(message = "Statements not allowed") {
        super(message);
    }
}

/**
 * The NotificationsNotAvailableError class represents an error when
 * subscribing to notifications is not allowed.
 * @extends ParticiapiError
 */
export class NotificationsNotAvailableError extends ParticiapiError {
    /**
     * The constructor returns a newly created NotificationsNotAvailableError
     * object.
     * @param {string} [message] - A human-readable description of the error.
     */
    constructor(message = "Notifications not available") {
        super(message);
    }
}

/**
 * The EmailAddressMissingError class represents an error when subscribing to
 * notifications is not possible due to a missing email address.
 * @extends ParticiapiError
 */
export class EmailAddressMissingError extends ParticiapiError {
    /**
     * The constructor returns a newly created EmailAddressMissingError object.
     * @param {string} [message] - A human-readable description of the error.
     */
    constructor(message = "Email address missing") {
        super(message);
    }
}

/**
 * The ResultsNotAvailableError class represents an error when retrieving
 * results is not possible because they are not available.
 * @extends ParticiapiError
 */
export class ResultsNotAvailableError extends ParticiapiError {
    /**
     * The constructor returns a newly created ResultsNotAvailableError object.
     * @param {string} [message] - A human-readable description of the error.
     */
    constructor(message = "Results not available") {
        super(message);
    }
}

/**
 * The SessionRequiredError class represents an error when a request is made
 * without a valid session.
 * @extends ParticiapiError
 */
export class SessionRequiredError extends ParticiapiError {
    /**
     * The constructor returns a newly created SessionRequiredError object.
     * @param {string} [message] - A human-readable description of the error.
     */
    constructor(message = "Session required") {
        super(message);
    }
}

/**
 * The HTTPError class represents an error due to an unknonw HTTP error.
 * @extends ParticiapiError
 */
export class HTTPError extends ParticiapiError {
    /**
     * The constructor returns a newly created HTTPError object.
     * @param {number} status - The HTTP status code returned by the server.
     * @param {string} [message] - A human-readable description of the error.
     */
    constructor(status, message = "Unknown HTTP error") {
        super(message);
        this.status = status;
    }
}

/**
 * The APIError class represents an error due to an unknown API error.
 * @extends HTTPError
 */
export class APIError extends HTTPError {
    /**
     * The constructor returns a newly created APIError object.
     * @param {number} status - The HTTP status code returned by the server.
     * @param {APIProblemDetails} problemDetails - The problem details JSON
     *     object returned by the server.
     */
    constructor(status, {type = "about:blank", title: message = "Unknown API error", detail = ""}) {
        super(status, message);
        /**
         * The type property contains a URI reference that identifies the
         * problem type returned by the server.
         */
        this.type = type;
        /**
         * The detail property contains a human-readable explanation specific
         * to this occurrence of the problem returned by the server.
         */
        this.detail = detail;
    }
}

/**
 * The AuthenticationRequiredError class represents an error caused by an
 * unauthenticated API request.
 * @extends APIError
 */
export class AuthenticationRequiredError extends APIError {
    /**
     * The constructor returns a newly created AuthenticationRequiredError
     *     object.
     * @param {number} status - The HTTP status code returned by the server.
     * @param {APIProblemDetails} problemDetails - The problem details JSON
     *     object returned by the server.
     */
    constructor(status, {type = "about:blank", title: message = "Authentication required", detail = ""}) {
        super(status, {type, title: message, detail});
    }
}

/**
  * The Vote enum represents all valid values for votes.
  * @enum {number}
  * @readonly
  * @see {@link ConversationClient.addVote}
  */
export const Vote = Object.freeze({
    Agree: -1,
    Neutral: 0,
    Disagree: 1,
});

/**
 * The Statement class represents a statement.
 */
export class Statement {
    /**
     * The constructor returns a newly created Statement object.
     * @param {APIStatement} statement - The statement JSON object returned by
     *     the server.
     */
    constructor({id, text, is_meta: isMeta, is_seed: isSeed}) {
        this.id = Number(id);
        this.text = text;
        this.isMeta = isMeta;
        this.isSeed = isSeed;
    }
}

/**
 * The Result class represents the result associated with a statement.
 */
export class Result {
    /**
     * The constructor returns a newly created Result object.
     * @param {APIResult} result - The result JSON object returned by the
     *     server.
     */
    constructor({statement_id: statementID, statement_text: statementText, value}) {
        /** The statement identifier. */
        this.statementID = Number(statementID);
        /** The statement text. */
        this.statementText = statementText;
        /**
         * The ratio of voters who either agreed or disagreed with this
         * statement.
         */
        this.value = value;
    }
}

/**
 * The GroupResults class represents the results of a group consisting of those
 * statments group members most strongly agree and disagree with.
 */
export class GroupResults {
    /**
     * The constructor returns a newly created GroupResults object.
     * @param {APIGroupResults} [groupResults={}] - The group result JSON
     *     object returned by the server.
     */
    constructor({agree: agree = [], disagree: disagree = []} = {}) {
        /** A list of statments group members most strongly agree with. */
        this.agree = [];
        /** A list of statments group members most strongly disagree with. */
        this.disagree = [];
        for (const o of agree) {
            this.agree.push(new Result(o));
        }
        for (const o of disagree) {
            this.disagree.push(new Result(o));
        }
    }
}

/**
 * The Results class represents all of the results of a conversation including
 * those of the majority and all groups.
 */
export class Results {
    /**
     * The constructor returns a newly created Results object.
     * @param {APIResults} [results={}] - The results JSON object returned by
     *     the server.
     */
    constructor({majority: majority = {}, groups: groups = []} = {}) {
        /** The group result for the majority of voters. */
        this.majority = new GroupResults(majority);
        /**
         * Group results of up to five groups of voters grouped by their voting
         * behavior.
         */
        this.groups = [];
        for (const o of groups) {
            this.groups.push(new GroupResults(o));
        }
    }
}

/**
 * The Notifications class represents the state of notification subscription of
 * a participant.
 */
export class Notifications {
    /**
     * The constructor returns a newly created Notifications object.
     * @param {APINotifications} notification - The notifications object
     *     returned by the server.
     */
    constructor({enabled = false, email = null}) {
        /** Whether notifications are enabled for the participant. */
        this.enabled = enabled;
        /** The email address of the participant. */
        this.email = email;
    }
}

/**
 * The Participant class represents data and settings specific to the current
 * participant.
 */
export class Participant {
    /**
     * The constructor returns a newly created Participant object.
     * @param {APIParticipant} [participant={}] - The participant JSON object
     *     returned by the server.
     */
    constructor({votes = [], statements = [], notifications = {}} = {}) {
        this.votes = new Set(votes);
        this.statements = new Set(statements);
        this.notifications = new Notifications(notifications);
    }
}

/**
 * The Conversation class represents the current conversation.
 */
export class Conversation {
    /**
     * The constructor returns a newly created Conversation object.
     * @param {string} conversationID - Conversation ID
     * @param {APIConversation} [conversation={}] - The conversation object
     *     returned by the server.
     */
    constructor(
        conversationID,
        {
            topic = "",
            description = "",
            description_html = "",
            is_active: isActive = false,
            statements_allowed: statementsAllowed = false,
            notifications_available: notificationsAvailable = false,
            results_available: resultsAvailable = false,
            seed_statements: seedStatements = {},
        } = {}
    ) {
        /** The identifier for the conversation. */
        this.id = conversationID;
        /** The topic of the conversation. */
        this.topic = topic;
        /** A longer description of the conversation. */
        this.description = description;
        const parser = new DOMParser();
        const doc = parser.parseFromString(description_html, "text/html");
        const fragment = new DocumentFragment();
        const nodes = doc.body.firstElementChild?.childNodes ?? [];
        fragment.append(...nodes);
        /** A longer description of the conversation as a Document. */
        this.descriptionDocument = fragment;
        /** Whether the conversation is active. */
        this.isActive = isActive;
        /** Whether participants are allowed to submit statements. */
        this.statementsAllowed = statementsAllowed;
        /** Whether email notitifcations are available. */
        this.notificationsAvailable = notificationsAvailable;
        /** Whether voting results are available. */
        this.resultsAvailable = resultsAvailable;
        /** The seed statemens of the conversation. */
        this.seedStatements = new Map();
        for (const [id, entry] of Object.entries(seedStatements)) {
            this.seedStatements.set(Number(id), new Statement(entry));
        }
    }
}

/**
 * The ConversationClient class is a client for interacting with a
 * conversation.
 */
export class ConversationClient {
    #sessionURL;
    #conversationURL;
    #participantURL;
    #votesBaseURL;
    #statementsURL;
    #resultsURL;
    #notificationsURL;
    #csrfToken;

    /**
     * The constructor returns a newly created ConversationClient object.
     * @param {URL|string} baseURL - The base URL of the server.
     * @param {string} conversationID - The identifier for a conversation.
     */
    constructor(baseURL, conversationID) {
        /**
         * @param {string} path
         * @returns {URL}
         */
        const urlWithPath = (path) => {
            const url = new URL(baseURL);
            const base = url.pathname.replace(/\/$/, '');
            url.pathname = base + path;
            return url;
        }

        /** The base URL of the server. */
        this.baseURL = new URL(baseURL);
        /** The identifier for the conversation. */
        this.conversationID = conversationID;

        /**
         * The URL for starting the authentication process. In case
         * authentication is required and the participant is not authenticated
         * the authentication process can be started by opening this URL in a
         * popup window.
         */
        this.loginURL = urlWithPath(`/auth/login`);

        this.#sessionURL = urlWithPath(`/api/session`);
        this.#conversationURL = urlWithPath(`/api/conversations/${this.conversationID}`);
        this.#participantURL = urlWithPath(`/api/conversations/${this.conversationID}/participant`);
        this.#votesBaseURL = urlWithPath(`/api/conversations/${this.conversationID}/votes`);
        this.#statementsURL = urlWithPath(`/api/conversations/${this.conversationID}/statements/`);
        this.#resultsURL = urlWithPath(`/api/conversations/${this.conversationID}/results/`);
        this.#notificationsURL = urlWithPath(`/api/conversations/${this.conversationID}/participant/notifications`);

        this.#csrfToken = "";

        /** Whether the client is authenticated. */
        this.authenticated = false;
        /** Whether the server requires authentication. */
        this.authenticationRequired = true;

        /** The conversation. */
        this.conversation = new Conversation(conversationID);
        /**
         * The statements of the conversation.
         * @type {Map<number, Statement>}
         */
        this.statements = new Map();
        /** The participant. */
        this.participant = new Participant();
        /** The voting results if available. */
        this.results = new Results();
    }

    /**
     * @param {Response} response
     */
    async #handleErrorResponse(response) {
        const contentType = response.headers.get("Content-Type");
        let problemDetails = {type: "", title: "", detail: ""};
        if (contentType !== null && contentType.includes("application/problem+json")) {
            problemDetails = await response.json();
        }

        switch (problemDetails.type) {
        case "tag:partici.app,2024:api:errors:authentication_required":
            this.#csrfToken = "";
            this.authenticated = false;
            this.authenticationRequired = true;
            this.participant = new Participant();
            this.statements = new Map();
            throw new AuthenticationRequiredError(response.status, problemDetails);
        case "tag:partici.app,2024:api:errors:email_address_missing":
            this.conversation.notificationsAvailable = false;
            throw new EmailAddressMissingError(problemDetails.detail);
        case "tag:partici.app,2024:api:errors:not_found":
            throw new NotFoundError(problemDetails.detail);
        case "tag:partici.app,2024:api:errors:statement_exists":
            throw new StatementExistsError(problemDetails.detail);
        case "tag:partici.app,2024:api:errors:conversation_inactive":
            this.conversation.isActive = false;
            throw new ConversationInactiveError(problemDetails.detail);
        case "tag:partici.app,2024:api:errors:statements_not_allowed":
            this.conversation.statementsAllowed = false;
            throw new StatementsNotAllowedError(problemDetails.detail);
        case "tag:partici.app,2024:api:errors:notifications_not_available":
            this.conversation.notificationsAvailable = false;
            throw new NotificationsNotAvailableError(problemDetails.detail);
        case "tag:partici.app,2024:api:errors:results_not_available":
            this.conversation.resultsAvailable = false;
            throw new ResultsNotAvailableError(problemDetails.detail);
        case "tag:partici.app,2024:api:errors:session_required":
            throw new SessionRequiredError(problemDetails.detail);
        default:
            if (response.status > 399) {
                throw new APIError(response.status, problemDetails);
            } else {
                throw new HTTPError(response.status, "unexpected HTTP status");
            }
        }
    }

    /**
     * @param {RequestInit} [options={}]
     */
    async #fetchConversation(options = {}) {
        const response = await fetch(this.#conversationURL,
            Object.assign({
                mode: "cors",
                credentials: "include",
            }, options)
        );
        if (!response.ok) {
            await this.#handleErrorResponse(response);
        }
        const data = await response.json();
        return new Conversation(this.conversationID, data);
    }

    /**
     * @param {URL} url
     * @param {RequestInit} [options={}]
     * @returns {Promise<object>}
     */
    async #fetchJSON(url, options = {}) {
        const response = await fetch(url,
            Object.assign({
                mode: "cors",
                credentials: "include",
            }, options)
        );
        if (!response.ok) {
            await this.#handleErrorResponse(response);
        }
        return response.json();
    }

    /**
     * @param {boolean} create
     * @param {RequestInit} [options={}]
     */
    async #updateSession(create = false, options = {}) {
        const url = create ? this.#sessionURL + "?create=true" : this.#sessionURL;
        const response = await fetch(url,
            Object.assign({
                method: "POST",
                mode: "cors",
                credentials: "include",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({})
            }, options)
        );
        if (!response.ok) {
            await this.#handleErrorResponse(response);
        }
        ({
            csrf_token: this.#csrfToken,
            authenticated: this.authenticated,
        } = await response.json());
    }

    /**
     * @param {string} method
     * @param {URL|string} url
     * @param {any} body
     * @param {RequestInit} [options={}]
     * @returns {Promise<Response>}
     */
    async #submitJSON(method, url, body, options = {}) {
        if (!this.conversation.isActive) {
            throw new ConversationInactiveError();
        }

        if (this.#csrfToken === "") {
            await this.#updateSession(true);
        }

        const response = await fetch(url,
            Object.assign({
                method: method,
                mode: "cors",
                credentials: "include",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": this.#csrfToken
                },
                body: JSON.stringify(body)
            }, options)
        );
        if (!response.ok) {
            await this.#handleErrorResponse(response);
        }
        return response;
    }

    /**
     * @param {RequestInit} [options={}]
     * @returns {Promise<Map<number, Statement>>}
     */
    async #fetchStatements(options = {}) {
        const data = await this.#fetchJSON(this.#statementsURL, options);
        const orderedEntries = Object.values(data);
        // shuffle using the modern Fisher-Yates algorithm
        for (let i = orderedEntries.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [orderedEntries[i], orderedEntries[j]] = [orderedEntries[j], orderedEntries[i]];
        }
        // sort meta statements before seed statements before all other statements
        orderedEntries.sort((a, b) => {
            if (a.is_meta && !b.is_meta) {
                return -1;
            } else if (!a.is_meta && b.is_meta) {
                return 1;
            }
            if (a.is_seed && !b.is_seed) {
                return -1;
            } else if (!a.is_seed && b.is_seed) {
                return 1;
            }
            return 0;
        });

        const statements = new Map();
        for (const entry of orderedEntries) {
            statements.set(entry.id, new Statement(entry));
        }
        return statements;
    }

    /**
     * @param {RequestInit} [options={}]
     * @returns {Promise<Results>}
     */
    async #fetchResults(options = {}) {
        const data = await this.#fetchJSON(this.#resultsURL, options);
        return new Results(data);
    }

    /**
     * @param {RequestInit} [options={}]
     * @returns {Promise<Participant>}
     */
    async #fetchParticipant(options = {}) {
        const data = await this.#fetchJSON(this.#participantURL, options);
        return new Participant(data);
    }

    /**
     * The pollStatements polls the server for new statements and updates the
     * statements property accordingly.  The availabilty of new statements is
     * indicated by the returned promise resolving to true.
     * @param {Object} [options={}] - Options to configure the underlying request.
     * @param {AbortSignal} [options.signal] - AbortSignal for canceling the request.
     * @returns {Promise<boolean>}
     */
    async pollStatements(options = {}) {
        const statements = await this.#fetchStatements(
            {signal: options.signal}
        );
        if (statements.size !== this.statements.size) {
            this.statements = statements;
            return true;
        }
        for (const id of statements.keys()) {
            if (!this.statements.has(id)) {
                return true;
            }
        }
        return false;
    }

    /**
     * The pollResults method polls the server for new voting results and
     * updates the results property accordingly.  The availabilty of new
     * results is indicated by the returned promise resolving to true.
     * @param {Object} [options={}] - Options to configure the underlying request.
     * @param {AbortSignal} [options.signal] - AbortSignal for canceling the request.
     * @returns {Promise<boolean>} Promise object indicating whether there are
     *     new results.
     */
    async pollResults(options = {}) {
        if (!this.conversation.resultsAvailable) {
            throw new ResultsNotAvailableError();
        }

        const results = await this.#fetchResults(
            {signal: options.signal}
        );

        /**
         * @param {GroupResults} oldGroup
         * @param {GroupResults} newGroup
         * @returns {boolean}
         */
        function groupResultChanged(oldGroup, newGroup) {
            if (newGroup.agree.length !== oldGroup.agree.length ||
                newGroup.disagree.length !== oldGroup.disagree.length) {
                return true;
            }
            const types = /** @type {Array.<keyof GroupResults>} */(["agree", "disagree"]);
            for (const type of types) {
                for (let i = 0; i < newGroup[type].length; i++) {
                    if (newGroup[type][i].statementID !== oldGroup[type][i].statementID ||
                        newGroup[type][i].value !== oldGroup[type][i].value) {
                        return true;
                    }
                }
            }
            return false;
        }
        if (groupResultChanged(results.majority, this.results.majority)) {
            this.results = results;
            return true;
        }
        if (results.groups.length !== this.results.groups.length) {
            this.results = results;
            return true;
        }
        for (let i = 0; i < results.groups.length; i++) {
            if (groupResultChanged(results.groups[i], this.results.groups[i])) {
                this.results = results;
                return true;
            }
        }
        return false;
    }

    /**
     * The addVote method adds a vote for the given statement.  A participant
     * may vote multiple times for the same statement, however only the last
     * vote will be counted.
     * @param {number|string} statementID - ID of the statement for which the
     *     vote cast.
     * @param {Vote} value - Value representing the vote.
     * @param {Object} [options={}] - Options to configure the underlying request.
     * @param {AbortSignal} [options.signal] - AbortSignal for canceling the
     *     request.
     */
    async addVote(statementID, value, options = {}) {
        await this.#submitJSON(
            "PUT",
            `${this.#votesBaseURL}/${statementID}`,
            {value},
            {signal: options.signal}
        );
        this.participant.votes.add(Number(statementID));
    }

    /**
     * The addStatement method ads a new statement.  The statement text must be
     * unique to the conversation.
     * @param {string} text - The statement text.
     * @param {Object} [options={}] - Options to configure the underlying request.
     * @param {AbortSignal} [options.signal] - AbortSignal for canceling the
     *     request.
     */
    async addStatement(text, options = {}) {
        if (!this.conversation.statementsAllowed) {
            throw new StatementsNotAllowedError();
        }

        const response = await this.#submitJSON(
            "POST",
            this.#statementsURL,
            {text},
            {signal: options.signal}
        );
        const data = await response.json();
        const statement = new Statement(data);
        this.statements.set(statement.id, statement);
        this.participant.statements.add(statement.id);
        // the server automatically votes with "agree" for users on their
        // submitted statements
        this.participant.votes.add(Number(statement.id));
    }

    /**
     * The setNotifications method sets the notifications preferences.
     * @param {boolean} enabled - Whether notifications are enabled.
     * @param {Object} [options={}] - Options to configure the underlying request.
     * @param {AbortSignal} [options.signal] - AbortSignal for canceling the
     *     request.
     */
    async setNotifications(enabled, options = {}) {
        if (!this.conversation.notificationsAvailable) {
            throw new NotificationsNotAvailableError();
        }

        await this.#submitJSON(
            "PUT",
            this.#notificationsURL,
            {enabled},
            {signal: options.signal}
        );
        this.participant.notifications.enabled = enabled;
    }

    /**
     * The init method initializes the conversation client and initially loads
     * the conversation.  It must als be called to update the client after
     * successful authentication.
     * @param {Object} [options={}] - Options to configure the underlying request.
     * @param {AbortSignal} [options.signal] - AbortSignal for canceling the request.
     */
    async init(options = {}) {
        this.conversation = await this.#fetchConversation(
            {signal: options.signal}
        );
        try {
            this.results = await this.#fetchResults(
                {signal: options.signal}
            );
        } catch(error) {
            if (!(error instanceof ResultsNotAvailableError)) {
                throw error;
            }
        }

        let statements;
        let participant;
        try {
            await this.#updateSession(false, {signal: options.signal});
            statements = await this.#fetchStatements({signal: options.signal});
        } catch (error) {
            if (error instanceof AuthenticationRequiredError) {
                return;
            }
            throw error;
        }
        this.statements = statements;
        this.authenticationRequired = false;

        try {
            participant = await this.#fetchParticipant(
                {signal: options.signal}
            );
        } catch (error) {
            if (error instanceof SessionRequiredError) {
                return;
            }
            throw error;
        }
        this.participant = participant;
    }

    /**
     * The currentStatement method returns the current statement.
     * Unauthenticated participants receive the first seed statement,
     * preferably a non-meta statement, if there are no seed statements at all
     * this will return null.  Authenticated participants get the first
     * statement which is not their own and which they have not voted on. If
     * there are no more statements this will return null.
     * @returns {?Statement}
     */
    currentStatement() {
        if (this.authenticationRequired) {
            for (const statement of this.conversation.seedStatements.values()) {
                if (!statement.isMeta) {
                    return statement;
                }
            }
            return this.conversation.seedStatements.values().next().value ?? null;
        }

        for (const [id, statement] of this.statements) {
            if (!this.participant.votes.has(id) &&
                !this.participant.statements.has(id)) {
                return statement;
            }
        }
        return null;
    }
}
