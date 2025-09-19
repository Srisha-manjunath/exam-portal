// placeholder for main JS - keep your original scripts here
// Enhanced main.js for Exam Portal

// Socket.IO connection (if available)
let socket = null;
if (typeof io !== 'undefined') {
    try {
        socket = io();
        console.log('Socket.IO connected');
    } catch (e) {
        console.log('Socket.IO not available');
    }
}

// Auto-save functionality for exam creation
function initAutoSave() {
    const form = document.getElementById('createExam');
    if (!form) return;
    
    // Save form data to localStorage every 30 seconds
    setInterval(() => {
        const formData = new FormData(form);
        const data = {};
        for (let [key, value] of formData.entries()) {
            if (!data[key]) data[key] = [];
            data[key].push(value);
        }
        try {
            localStorage.setItem('exam_draft', JSON.stringify(data));
        } catch (e) {
            console.log('Auto-save not available');
        }
    }, 30000);
    
    // Restore form data on page load
    try {
        const saved = localStorage.getItem('exam_draft');
        if (saved) {
            const data = JSON.parse(saved);
            // Restore form fields...
            console.log('Draft restored');
        }
    } catch (e) {
        console.log('No draft to restore');
    }
}

// Enhanced question management
function addQuestion() {
    const container = document.getElementById('questions');
    if (!container) return;
    
    const questionCount = container.children.length + 1;
    const div = document.createElement('div');
    div.className = 'mb-4 p-4 bg-white rounded-lg shadow border-l-4 border-indigo-400';
    div.innerHTML = `
        <div class="flex justify-between items-center mb-2">
            <h4 class="font-semibold text-gray-700">Question ${questionCount}</h4>
            <button type="button" onclick="removeQuestion(this)" class="text-red-500 hover:text-red-700">
                <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                </svg>
            </button>
        </div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Question Text</label>
        <textarea name="qtext[]" rows="3" class="w-full p-2 border border-gray-300 rounded-md mb-3 focus:ring-indigo-500 focus:border-indigo-500" placeholder="Enter your question here..." required></textarea>
        
        <label class="block text-sm font-medium text-gray-700 mb-1">Answer Key (for auto-grading)</label>
        <textarea name="qkey[]" rows="2" class="w-full p-2 border border-gray-300 rounded-md mb-3 focus:ring-indigo-500 focus:border-indigo-500" placeholder="Expected answer or keywords..."></textarea>
        
        <label class="block text-sm font-medium text-gray-700 mb-1">Marks</label>
        <input name="qmarks[]" type="number" min="1" max="100" value="1" class="w-20 p-2 border border-gray-300 rounded-md focus:ring-indigo-500 focus:border-indigo-500">
    `;
    
    container.appendChild(div);
    
    // Scroll to new question
    div.scrollIntoView({ behavior: 'smooth', block: 'center' });
    
    // Focus on question text
    div.querySelector('textarea[name="qtext[]"]').focus();
}

function removeQuestion(button) {
    const questionDiv = button.closest('.mb-4');
    if (questionDiv) {
        questionDiv.remove();
        renumberQuestions();
    }
}

function renumberQuestions() {
    const questions = document.querySelectorAll('#questions > div');
    questions.forEach((question, index) => {
        const title = question.querySelector('h4');
        if (title) {
            title.textContent = `Question ${index + 1}`;
        }
    });
}

// Exam timer functionality
function initExamTimer() {
    const timerElement = document.getElementById('exam-timer');
    if (!timerElement) return;
    
    const examDuration = parseInt(timerElement.dataset.duration) || 3600; // Default 1 hour
    let timeLeft = examDuration;
    
    function updateTimer() {
        const hours = Math.floor(timeLeft / 3600);
        const minutes = Math.floor((timeLeft % 3600) / 60);
        const seconds = timeLeft % 60;
        
        const display = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        timerElement.textContent = display;
        
        // Change color when time is running low
        if (timeLeft < 300) { // Less than 5 minutes
            timerElement.className = 'text-red-600 font-bold';
        } else if (timeLeft < 600) { // Less than 10 minutes
            timerElement.className = 'text-yellow-600 font-bold';
        }
        
        if (timeLeft <= 0) {
            clearInterval(timerInterval);
            alert('Time is up! Your exam will be submitted automatically.');
            document.getElementById('exam-form')?.submit();
        }
        
        timeLeft--;
    }
    
    const timerInterval = setInterval(updateTimer, 1000);
    updateTimer(); // Initial call
}

// Tab visibility detection for exam integrity
function initTabMonitoring() {
    if (!document.getElementById('exam-form')) return;
    
    let tabSwitchCount = 0;
    const maxTabSwitches = 3;
    
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            tabSwitchCount++;
            
            // Send notification to staff if socket is available
            if (socket) {
                socket.emit('student_tab_switch', {
                    student: document.body.dataset.studentId,
                    count: tabSwitchCount,
                    timestamp: new Date().toISOString()
                });
            }
            
            // Warning to student
            if (tabSwitchCount >= maxTabSwitches) {
                alert('Warning: Multiple tab switches detected. Your exam may be flagged for review.');
            } else {
                console.log(`Tab switch detected (${tabSwitchCount}/${maxTabSwitches})`);
            }
        }
    });
}

// Real-time notifications for staff
function initStaffNotifications() {
    if (!socket || !document.body.classList.contains('staff-dashboard')) return;
    
    // Join staff room
    socket.emit('join_staff');
    
    socket.on('submission', function(data) {
        showNotification(`New submission from ${data.student}: ${data.marks} marks`, 'success');
    });
    
    socket.on('tab_switch', function(data) {
        showNotification(`Student ${data.student} switched tabs (${data.count} times)`, 'warning');
    });
}

// Notification system
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 p-4 rounded-lg shadow-lg z-50 transform transition-all duration-300 translate-x-full`;
    
    const typeClasses = {
        success: 'bg-green-500 text-white',
        warning: 'bg-yellow-500 text-white',
        error: 'bg-red-500 text-white',
        info: 'bg-blue-500 text-white'
    };
    
    notification.className += ` ${typeClasses[type] || typeClasses.info}`;
    notification.innerHTML = `
        <div class="flex items-center">
            <span class="mr-2">${message}</span>
            <button onclick="this.parentElement.parentElement.remove()" class="ml-2 text-white hover:text-gray-200">×</button>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => {
        notification.classList.remove('translate-x-full');
    }, 100);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        notification.classList.add('translate-x-full');
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

// Form validation enhancement
function initFormValidation() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let isValid = true;
            
            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    isValid = false;
                    field.classList.add('border-red-500');
                    field.addEventListener('input', function() {
                        if (this.value.trim()) {
                            this.classList.remove('border-red-500');
                        }
                    });
                } else {
                    field.classList.remove('border-red-500');
                }
            });
            
            if (!isValid) {
                e.preventDefault();
                showNotification('Please fill in all required fields', 'error');
            }
        });
    });
}

// Character count for textareas
function initCharacterCount() {
    const textareas = document.querySelectorAll('textarea');
    
    textareas.forEach(textarea => {
        const maxLength = textarea.getAttribute('maxlength');
        if (!maxLength) return;
        
        const counter = document.createElement('div');
        counter.className = 'text-sm text-gray-500 mt-1 text-right';
        textarea.parentNode.appendChild(counter);
        
        function updateCount() {
            const remaining = maxLength - textarea.value.length;
            counter.textContent = `${remaining} characters remaining`;
            
            if (remaining < 10) {
                counter.className = 'text-sm text-red-500 mt-1 text-right';
            } else {
                counter.className = 'text-sm text-gray-500 mt-1 text-right';
            }
        }
        
        textarea.addEventListener('input', updateCount);
        updateCount();
    });
}

// Initialize everything when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initAutoSave();
    initExamTimer();
    initTabMonitoring();
    initStaffNotifications();
    initFormValidation();
    initCharacterCount();
    
    console.log('Exam Portal initialized');
});

// Prevent right-click during exams (basic security)
if (document.getElementById('exam-form')) {
    document.addEventListener('contextmenu', function(e) {
        e.preventDefault();
    });
    
    document.addEventListener('keydown', function(e) {
        // Prevent F12, Ctrl+Shift+I, etc.
        if (e.key === 'F12' || 
            (e.ctrlKey && e.shiftKey && e.key === 'I') ||
            (e.ctrlKey && e.shiftKey && e.key === 'C') ||
            (e.ctrlKey && e.key === 'u')) {
            e.preventDefault();
        }
    });
}