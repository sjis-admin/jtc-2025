/**
 * Enhanced HTMX Integration for Registration Form
 * This script provides better handling of HTMX requests and responses
 */

// HTMX Configuration
document.addEventListener('DOMContentLoaded', function() {
    // Configure HTMX defaults
    if (typeof htmx !== 'undefined') {
        htmx.config.globalViewTransitions = true;
        htmx.config.defaultSwapDelay = 100;
        htmx.config.defaultSettleDelay = 100;
    }

    // Enhanced error handling for HTMX requests
    document.body.addEventListener('htmx:responseError', function(event) {
        console.error('HTMX Response Error:', event.detail);
        
        // Show user-friendly error message
        if (event.target.id === 'group-display') {
            event.target.innerHTML = '<div class="w-full px-4 py-2 border border-red-300 rounded-lg bg-red-50 text-red-600">Error loading group information</div>';
        }
        
        // Hide loading indicators
        hideAllLoadingIndicators();
    });

    // Network error handling
    document.body.addEventListener('htmx:sendError', function(event) {
        console.error('HTMX Network Error:', event.detail);
        
        // Show network error message
        if (event.target.id === 'group-display') {
            event.target.innerHTML = '<div class="w-full px-4 py-2 border border-red-300 rounded-lg bg-red-50 text-red-600">Network error. Please check your connection.</div>';
        }
        
        hideAllLoadingIndicators();
    });

    // Request timeout handling
    document.body.addEventListener('htmx:timeout', function(event) {
        console.warn('HTMX Request Timeout:', event.detail);
        
        if (event.target.id === 'group-display') {
            event.target.innerHTML = '<div class="w-full px-4 py-2 border border-yellow-300 rounded-lg bg-yellow-50 text-yellow-700">Request timed out. Please try again.</div>';
        }
        
        hideAllLoadingIndicators();
    });

    // Before request handling
    document.body.addEventListener('htmx:beforeRequest', function(event) {
        // Add loading states
        if (event.target.id === 'group-display') {
            showLoadingIndicator('group-loading');
            
            // Add loading class to the target element
            event.target.classList.add('htmx-request', 'animate-pulse');
        }
        
        if (event.target.id === 'event-list') {
            showLoadingIndicator('events-loading');
        }
    });

    // After request handling
    document.body.addEventListener('htmx:afterRequest', function(event) {
        // Remove loading states
        if (event.target.id === 'group-display') {
            hideLoadingIndicator('group-loading');
            event.target.classList.remove('htmx-request', 'animate-pulse');
        }
        
        if (event.target.id === 'event-list') {
            hideLoadingIndicator('events-loading');
        }
    });

    // Custom trigger handling for group display
    document.body.addEventListener('updateGroupDisplay', function(event) {
        const groupDisplay = document.getElementById('group-display');
        if (!groupDisplay || !event.detail.value) return;

        const value = event.detail.value;
        let cssClasses = "w-full px-4 py-2 border rounded-lg transition-all duration-200";

        // Determine styling based on content
        if (value === 'Select grade first') {
            cssClasses += " border-gray-300 bg-gray-50 text-gray-500";
        } else if (value.includes('Invalid') || value.includes('Error')) {
            cssClasses += " border-red-300 bg-red-50 text-red-600";
        } else {
            cssClasses += " border-green-300 bg-green-50 text-green-700 font-medium";
        }

        // Update with animation
        groupDisplay.style.opacity = '0.5';
        setTimeout(() => {
            groupDisplay.className = cssClasses;
            groupDisplay.textContent = value;
            groupDisplay.style.opacity = '1';
        }, 150);
    });

    // Grade selection enhancement
    const gradeSelect = document.getElementById('id_grade');
    if (gradeSelect) {
        // Debounce function to prevent rapid API calls
        let gradeChangeTimeout;
        
        gradeSelect.addEventListener('change', function() {
            clearTimeout(gradeChangeTimeout);
            
            const selectedValue = this.value;
            console.log('Grade selection changed to:', selectedValue);
            
            if (selectedValue) {
                // Clear previous selections
                clearEventSelections();
                
                // Debounced update
                gradeChangeTimeout = setTimeout(() => {
                    // Trigger both group and events update
                    triggerGroupUpdate();
                    triggerEventsUpdate();
                }, 200);
            } else {
                // Reset to initial state
                resetGroupDisplay();
                clearEventSelections();
            }
        });
    }
});

// Utility functions
function showLoadingIndicator(elementId) {
    const indicator = document.getElementById(elementId);
    if (indicator) {
        indicator.classList.remove('hidden');
    }
}

function hideLoadingIndicator(elementId) {
    const indicator = document.getElementById(elementId);
    if (indicator) {
        indicator.classList.add('hidden');
    }
}

function hideAllLoadingIndicators() {
    const indicators = document.querySelectorAll('[id$="-loading"]');
    indicators.forEach(indicator => {
        indicator.classList.add('hidden');
    });
}

function clearEventSelections() {
    const eventRadios = document.querySelectorAll('.event-option-radio');
    eventRadios.forEach(radio => {
        radio.checked = false;
    });
    
    // Reset visual styling
    const eventCards = document.querySelectorAll('.event-card-container label');
    eventCards.forEach(label => {
        label.classList.remove('border-indigo-600', 'shadow-lg', 'bg-indigo-50');
        label.classList.add('border-gray-200');
    });
    
    // Reset total amount
    const totalAmount = document.getElementById('total-amount');
    if (totalAmount) {
        totalAmount.innerHTML = '<span class="text-2xl font-bold text-gray-500">৳0.00</span>';
    }
}

function triggerGroupUpdate() {
    const groupDisplay = document.getElementById('group-display');
    if (groupDisplay) {
        htmx.trigger(groupDisplay, 'change from:#id_grade');
    }
}

function triggerEventsUpdate() {
    const eventList = document.getElementById('event-list');
    if (eventList) {
        htmx.trigger(eventList, 'change from:#id_grade');
    }
}

function resetGroupDisplay() {
    const groupDisplay = document.getElementById('group-display');
    if (groupDisplay) {
        groupDisplay.className = "w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500";
        groupDisplay.textContent = "Select grade first";
    }
}

// Enhanced form validation
function validateForm() {
    const gradeSelect = document.getElementById('id_grade');
    const eventRadios = document.querySelectorAll('.event-option-radio:checked');
    
    if (!gradeSelect.value) {
        showValidationError('Please select a grade first.', gradeSelect);
        return false;
    }
    
    if (eventRadios.length === 0) {
        showValidationError('Please select at least one event.');
        return false;
    }
    
    return true;
}

function showValidationError(message, element = null) {
    // Create or update error message
    let errorDiv = document.getElementById('validation-error');
    
    if (!errorDiv) {
        errorDiv = document.createElement('div');
        errorDiv.id = 'validation-error';
        errorDiv.className = 'fixed top-4 right-4 bg-red-500 text-white px-6 py-3 rounded-lg shadow-lg z-50';
        document.body.appendChild(errorDiv);
    }
    
    errorDiv.innerHTML = `
        <div class="flex items-center">
            <i class="fas fa-exclamation-circle mr-2"></i>
            <span>${message}</span>
            <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-white hover:text-gray-200">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `;
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        if (errorDiv && errorDiv.parentElement) {
            errorDiv.remove();
        }
    }, 5000);
    
    // Focus on problematic element
    if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        element.focus();
    }
}

// Enhanced total calculation
function enhancedTotalCalculation() {
    const form = document.querySelector('form');
    if (!form) return;
    
    // Listen for event selection changes
    form.addEventListener('change', function(event) {
        if (event.target.classList.contains('event-option-radio')) {
            // Add visual feedback
            updateEventSelection(event.target);
            
            // Trigger total calculation with delay to ensure visual update
            setTimeout(() => {
                htmx.trigger(event.target, 'change');
            }, 100);
        }
    });
}

function updateEventSelection(radio) {
    // Remove previous selections styling
    document.querySelectorAll('.event-card-container label').forEach(label => {
        label.classList.remove('border-indigo-600', 'shadow-lg', 'bg-indigo-50');
        label.classList.add('border-gray-200');
    });
    
    // Add selection styling to current
    if (radio.checked) {
        const card = radio.closest('.event-card-container');
        if (card) {
            const label = card.querySelector('label');
            if (label) {
                label.classList.remove('border-gray-200');
                label.classList.add('border-indigo-600', 'shadow-lg', 'bg-indigo-50');
            }
        }
    }
}

// Initialize enhanced functionality
document.addEventListener('DOMContentLoaded', function() {
    enhancedTotalCalculation();
    
    // Add form submission validation
    const form = document.querySelector('form[method="post"]');
    if (form) {
        form.addEventListener('submit', function(event) {
            if (!validateForm()) {
                event.preventDefault();
                return false;
            }
        });
    }
});

// Export functions for global access
window.RegistrationFormHelpers = {
    validateForm,
    clearEventSelections,
    triggerGroupUpdate,
    triggerEventsUpdate,
    showValidationError
};