// Function to copy text to clipboard
function setPasteBufferToText(text) {
    navigator.clipboard.writeText(text).catch(err => {
        console.error('Failed to copy text: ', err);
    });
}

class Terminals {
    paste_to_terminal(text, session) {
        if (parent && parent.educates) {
            parent.educates.paste_to_terminal(text, session);
        } else {
            console.log('paste_to_terminal:', text, session);
        }
    }

    paste_to_all_terminals(text) {
        if (parent && parent.educates) {
            parent.educates.paste_to_all_terminals(text);
        } else {
            console.log('paste_to_all_terminals:', text);
        }
    }

    execute_in_terminal(command, session, clear) {
        if (!command) {
            return;
        }

        if (parent && parent.educates) {
            parent.educates.execute_in_terminal(command, session, clear);
        } else {
            console.log('execute_in_terminal:', command, session, clear);
        }
    }

    execute_in_all_terminals(command, clear) {
        if (!command) {
            return;
        }

        if (parent && parent.educates) {
            parent.educates.execute_in_all_terminals(command, clear);
        } else {
            console.log('execute_in_all_terminals:', command, clear);
        }
    }

    select_terminal(session) {
        if (parent && parent.educates) {
            return parent.educates.select_terminal(session);
        } else {
            console.log('select_terminal:', session);
            return false;
        }
    }

    clear_terminal(session) {
        if (parent && parent.educates) {
            parent.educates.clear_terminal(session);
        } else {
            console.log('clear_terminal:', session);
        }
    }

    clear_all_terminals() {
        if (parent && parent.educates) {
            parent.educates.clear_all_terminals();
        } else {
            console.log('clear_all_terminals');
        }
    }

    interrupt_terminal(session) {
        if (parent && parent.educates) {
            parent.educates.interrupt_terminal(session);
        } else {
            console.log('interrupt_terminal:', session);
        }
    }

    interrupt_all_terminals() {
        if (parent && parent.educates) {
            parent.educates.interrupt_all_terminals();
        } else {
            console.log('interrupt_all_terminals');
        }
    }
}

const terminals = new Terminals();

// Function to get parent dashboard if it exists
function parent_dashboard() {
    if (parent && parent.educates) {
        return parent.educates.dashboard;
    }
}

// Function to preview an image
function preview_image(src, title) {
    const dashboard = parent_dashboard();

    if (!dashboard) {
        const previewElement = document.getElementById('preview-image-element');
        const previewTitle = document.getElementById('preview-image-title');
        const previewDialog = document.getElementById('preview-image-dialog');

        if (previewElement && previewTitle && previewDialog) {
            previewElement.setAttribute('src', src);
            previewTitle.textContent = title;
            const modal = new bootstrap.Modal(previewDialog);
            modal.show();
        }
    } else {
        dashboard.preview_image(src, title);
    }
}

// Initialize inline copy functionality
document.addEventListener('DOMContentLoaded', function () {
    // Find all inline-copy elements
    const inlineCopyElements = document.querySelectorAll('.inline-copy');

    inlineCopyElements.forEach(element => {
        // Find the preceding code element
        const target = element.previousElementSibling;

        if (target && target.tagName === 'CODE') {
            // Add click event listener to the code element
            target.addEventListener('click', () => {
                // Copy the text content
                setPasteBufferToText(target.textContent);

                // Update the icon classes
                element.classList.add('fas');
                element.classList.remove('far');

                // Reset the icon after 250ms
                setTimeout(() => {
                    element.classList.add('far');
                    element.classList.remove('fas');
                }, 250);
            });
        }
    });

    // Handle external links in page content
    const pageContentLinks = document.querySelectorAll('section.page-content a');
    pageContentLinks.forEach(anchor => {
        if (!(location.hostname === anchor.hostname || !anchor.hostname.length)) {
            anchor.setAttribute('target', '_blank');
        }
    });

    // Handle image preview in page content
    const pageContentImages = document.querySelectorAll('section.page-content img');
    pageContentImages.forEach(image => {
        image.addEventListener('click', () => {
            preview_image(image.src, image.alt);
        });
    });
});

// Exported functions

function expose_dashboard(name, done = () => { }, fail = (_) => { }) {
    let dashboard = parent_dashboard();

    if (!dashboard) {
        return fail("Dashboard is not available");
    }

    if (!dashboard.expose_dashboard(name)) {
        return fail("Dashboard does not exist");
    }

    done();
}

function execute_in_terminal(command, session, clear = false, done = () => { }, fail = (_) => { }) {
    let terminals = parent_terminals()

    if (!terminals)
        return fail("Terminals are not available")

    session = session || "1";

    if (session == "*") {
        expose_dashboard("terminal");
        terminals.execute_in_all_terminals(command, clear);
    } else {
        expose_terminal(id);
        terminals.execute_in_terminal(command, id, clear);
    }

    done();
}

// Table of clickable actions and their handlers
const clickable_action_handlers = {};
const clickable_actions = {};

function register_clickable_action(action, args) {
    const element = document.getElementById(action);
    const handler = element.dataset.handler;
    const callback = clickable_action_handlers[handler];

    console.log("register_clickable_action", handler, action);

    clickable_actions[action] = function () {
        callback(element, args);
    };
}

function clickable_action_handler(event) {
    const element = event.currentTarget;
    const action = element.id;
    const handler = element.dataset.handler;

    console.log("clickable_action_handler", handler, action);

    const callback = clickable_actions[action];

    if (callback) {
        callback();
    }
}

clickable_action_handlers["terminal:execute"] = function (element, args) {
    const defaults = {
        "command": undefined,
        "session": "1",
        "clear": false,
    }

    args = { ...defaults, ...args }

    const command = args.command;
    const session = args.session || "1";
    const clear = args.clear;

    if (!command) {
        return;
    }

    terminals.execute_in_terminal(command, session, clear);
}

clickable_action_handlers["terminal:execute-all"] = function (element, args) {
    const defaults = {
        "command": undefined,
        "clear": false,
    }

    args = { ...defaults, ...args }

    const command = args.command;
    const clear = args.clear;

    if (!command) {
        return;
    }

    terminals.execute_in_all_terminals(command, clear);
}

clickable_action_handlers["terminal:interrupt"] = function (element, args) {
    const defaults = {
        "session": "1",
    }

    args = { ...defaults, ...args }

    const session = args.session;

    terminals.interrupt_terminal(session);
}

clickable_action_handlers["terminal:interrupt-all"] = function (element, args) {
    terminals.interrupt_all_terminals();
}

clickable_action_handlers["terminal:clear"] = function (element, args) {
    const defaults = {
        "session": "1",
    }

    args = { ...defaults, ...args }

    const session = args.session;

    terminals.clear_terminal(session);
}

clickable_action_handlers["terminal:clear-all"] = function (element) {
    terminals.clear_all_terminals();
}
