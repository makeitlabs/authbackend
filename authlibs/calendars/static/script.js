/**
 * Booking Control Logic - Continuous Scrolling & Multi-Day Support
 */

class BookingControl {
    constructor() {
        // Configuration
        this.slotDuration = 30; // minutes
        this.startHour = 0;     // 00:00
        this.endHour = 24;      // 24:00 (Next day 00:00)

        // State
        this.loadedStart = new Date(); // Earliest loaded date
        this.loadedEnd = new Date();   // Latest loaded date
        this.selection = null; // { start: Date, end: Date }
        this.isDragging = false;
        this.isResizing = false;
        this.resizeAnchor = null; // Timestamp
        this.dragStartTime = null; // Timestamp
        this.autoScrollSpeed = 0;
        this.animationFrameId = null;
        this.currentUser = null;
        this.editingBooking = null; // The booking currently being edited

        // Drag-to-scroll state
        this.isScrollDragging = false;
        this.scrollDragStartY = 0;
        this.scrollDragStartScroll = 0;
        this.scrollHintStartTime = Date.now();

        // Normalize dates to midnight
        this.loadedStart.setHours(0, 0, 0, 0);
        this.loadedEnd.setHours(0, 0, 0, 0);

        // Load Data from Server (Jinja)
        this.bookings = this.loadBookings();

        // DOM Elements
        this.elements = {
            prevDateBtn: document.getElementById('prevDate'),
            nextDateBtn: document.getElementById('nextDate'),
            dateDisplay: document.getElementById('dateDisplay'),
            datePicker: document.getElementById('datePicker'),
            backBtn: document.getElementById('backBtn'),
            timeGrid: document.getElementById('timeGrid'),
            scrollArea: document.getElementById('scrollArea'),
            scrollHint: document.getElementById('scrollHint'),
            selectionDisplay: document.getElementById('selectionDisplay'),
            bookBtn: document.getElementById('bookBtn'),
            cancelBtn: document.getElementById('cancelBtn'),
            myBookingsBtn: document.getElementById('myBookingsBtn'),
            myBookingsList: document.getElementById('myBookingsList'),
            // Modals
            bookingModal: document.getElementById('bookingModal'),
            deleteModal: document.getElementById('deleteModal'),
            bookingModalTitle: document.getElementById('bookingModalTitle'),
            bookingDescription: document.getElementById('bookingDescription'),
            confirmBookingBtn: document.getElementById('confirmBookingBtn'),
            cancelBookingModal: document.getElementById('cancelBookingModal'),
            confirmDeleteBtn: document.getElementById('confirmDeleteBtn'),
            cancelDeleteModal: document.getElementById('cancelDeleteModal')
        };

        this.init();
    }

    init() {
        // Initial Load: Yesterday, Today, Tomorrow
        const yesterday = new Date(this.loadedStart);
        yesterday.setDate(yesterday.getDate() - 1);
        this.renderDay(yesterday, 'prepend');
        this.loadedStart = yesterday;

        this.renderDay(new Date(), 'append'); // Today

        const tomorrow = new Date(this.loadedEnd);
        tomorrow.setDate(tomorrow.getDate() + 1);
        this.renderDay(tomorrow, 'append');
        this.loadedEnd = tomorrow;

        this.attachEventListeners();

        // Scroll to Current Time Today
        const now = new Date();
        const currentHour = now.getHours();
        this.scrollToTime(now, currentHour);

        // Initial Header Update
        this.updateHeaderDate();

        // Render My Bookings List
        this.renderMyBookingsList();
    }

    loadBookings() {
        const data = window.SERVER_DATA || { bookings: [] };
        this.currentUser = data.currentUser;
        return data.bookings.map(b => ({
            id: Math.random().toString(36).substr(2, 9), // Generate simple ID
            calendar_id: b.calendar_id, // Store calendar_id from server
            start: new Date(b.start),
            end: new Date(b.end),
            user: b.user,
            description: b.description,
            isMine: b.isMine
        }));
    }

    renderDay(date, position = 'append') {
        const dayStart = new Date(date);
        dayStart.setHours(0, 0, 0, 0);

        const section = document.createElement('div');
        section.className = 'day-section';
        section.dataset.date = this.toDateKey(dayStart);

        // Day Separator
        const separator = document.createElement('div');
        separator.className = 'day-separator';
        const options = { weekday: 'long', month: 'short', day: 'numeric' };
        separator.textContent = dayStart.toLocaleDateString('en-US', options);
        section.appendChild(separator);

        // Calculate total slots
        const totalMinutes = (this.endHour - this.startHour) * 60;
        const totalSlots = totalMinutes / this.slotDuration;

        for (let i = 0; i < totalSlots; i++) {
            const slotTime = new Date(dayStart);
            slotTime.setMinutes(slotTime.getMinutes() + (i * this.slotDuration));

            // Time Label (every hour)
            if (i % 2 === 0) {
                const label = document.createElement('div');
                label.className = 'time-label';
                if (i === 0) label.classList.add('start-of-day');
                label.textContent = this.formatTime(slotTime);
                label.style.gridColumn = '1';
                label.style.gridRow = `${i + 2}`;
                section.appendChild(label);
            }

            // Slot
            const slot = document.createElement('div');
            slot.className = 'time-slot';

            // Check if slot is in the past
            const now = new Date();
            if (slotTime < now) {
                slot.classList.add('past-slot');
            }

            slot.dataset.time = slotTime.getTime(); // Use timestamp for easier logic
            slot.style.gridColumn = '2';
            slot.style.gridRow = `${i + 2}`;

            section.appendChild(slot);
        }

        // Render Bookings for this day
        this.renderBookingsForDay(section, dayStart);

        if (position === 'prepend') {
            this.elements.timeGrid.prepend(section);
        } else {
            this.elements.timeGrid.appendChild(section);
        }
    }

    renderBookingsForDay(section, dayStart) {
        // Filter bookings for this day
        const dayEnd = new Date(dayStart);
        dayEnd.setHours(24, 0, 0, 0);

        this.bookings.forEach(booking => {
            // Check overlap with this day
            if (booking.end <= dayStart || booking.start >= dayEnd) return;

            // Calculate start/end relative to this day
            const start = booking.start < dayStart ? dayStart : booking.start;
            const end = booking.end > dayEnd ? dayEnd : booking.end;

            const diffStart = (start - dayStart) / 1000 / 60;
            const startIndex = Math.floor(diffStart / this.slotDuration);

            const diffEnd = (end - start) / 1000 / 60;
            const span = Math.ceil(diffEnd / this.slotDuration);

            const card = document.createElement('div');
            card.className = 'booking-event';
            card.dataset.id = booking.id;

            if (booking.isMine) {
                card.classList.add('mine');
                // Click to edit
                card.addEventListener('click', (e) => this.handleBookingClick(e, booking));
            }

            // If currently editing this booking, hide it
            if (this.editingBooking && this.editingBooking.id === booking.id) {
                card.classList.add('hidden-editing');
            }

            card.style.gridColumn = '2';
            card.style.gridRow = `${startIndex + 2} / span ${span}`; // +2 for separator

            const userEl = document.createElement('div');
            userEl.className = 'booking-user';
            userEl.textContent = booking.user;

            const descEl = document.createElement('div');
            descEl.className = 'booking-desc';
            descEl.textContent = booking.description;

            card.appendChild(userEl);
            card.appendChild(descEl);

            section.appendChild(card);
        });
    }

    handleBookingClick(e, booking) {
        e.stopPropagation(); // Prevent triggering grid click

        // Enter Edit Mode
        this.editingBooking = booking;

        // Hide the card(s) for this booking
        document.querySelectorAll(`.booking-event[data-id="${booking.id}"]`).forEach(el => {
            el.classList.add('hidden-editing');
        });

        // Set selection to booking range
        this.updateSelection(booking.start.getTime(), booking.end.getTime() - (this.slotDuration * 60 * 1000));
    }

    scrollToTime(date, hour) {
        // Legacy method kept for init, but using scrollToDate mostly
        date.setHours(0, 0, 0, 0);
        const dateStr = this.toDateKey(date);
        const section = document.querySelector(`.day-section[data-date="${dateStr}"]`);

        if (section) {
            const offset = (hour * 2 * 40) + 40;
            const sectionTop = section.offsetTop;
            this.elements.scrollArea.scrollTop = sectionTop + offset;
        }
    }

    scrollToDate(date, ignoreOffset = false) {
        let targetDate = new Date(date);
        if (!ignoreOffset) {
            // Target 10am using setHours (DST-safe)
            targetDate.setHours(10, 0, 0, 0);
        }

        // Find slot closest to target time
        const slot = document.querySelector(`.time-slot[data-time="${targetDate.getTime()}"]`);

        if (slot) {
            slot.scrollIntoView({ block: 'center', behavior: 'auto' });
        } else {
            const dayStart = new Date(date);
            dayStart.setHours(0, 0, 0, 0);

            // Ensure day is loaded
            if (dayStart < this.loadedStart) {
                this.renderDay(dayStart, 'prepend');
                this.loadedStart = dayStart;
            } else if (dayStart >= this.loadedEnd) {
                this.renderDay(dayStart, 'append');
                const nextDay = new Date(dayStart);
                nextDay.setDate(nextDay.getDate() + 1);
                this.loadedEnd = nextDay;
            }

            // Try finding section again after load
            setTimeout(() => {
                const section = document.querySelector(`.day-section[data-date="${this.toDateKey(dayStart)}"]`);
                if (section) {
                    // Scroll to 10am instead of start
                    const offset = (10 * 60 * (40 / 30)); // 10 hours * 60 min * px/min roughly. 
                    // Actually logic is simpler: 10 hours * 2 slots/hr * 40px/slot = 800px.
                    const tenAmOffset = (10 * 2 * 40) + 40; // +40 header
                    this.elements.scrollArea.scrollTop = section.offsetTop + tenAmOffset;
                }
            }, 50);
        }
    }

    formatTime(date) {
        const hours = date.getHours();
        const minutes = date.getMinutes();
        if (hours === 12 && minutes === 0) return 'Noon';
        if (hours === 0 && minutes === 0) return 'Midnight';
        return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    }

    isSlotBooked(time) {
        // Check if time is within any booking
        // EXCLUDE the booking being edited
        return this.bookings.some(booking => {
            if (this.editingBooking && booking.id === this.editingBooking.id) return false;
            return time >= booking.start && time < booking.end;
        });
    }

    attachEventListeners() {
        // Scroll Event for Infinite Scroll & Header Update
        this.elements.scrollArea.addEventListener('scroll', () => {
            this.handleInfiniteScroll();
            this.updateHeaderDate();
            this.hideScrollHint();
        });

        // Nav Buttons (Jump to Prev/Next Day)
        this.elements.prevDateBtn.addEventListener('click', () => {
            const currentTopDate = this.getVisibleDate();
            const prevDay = new Date(currentTopDate);
            prevDay.setDate(prevDay.getDate() - 1);

            // Ensure rendered
            if (prevDay < this.loadedStart) {
                this.renderDay(prevDay, 'prepend');
                this.loadedStart = prevDay;
            }
            this.scrollToTime(prevDay, 9);
            this.updateHeaderDate();
        });

        this.elements.nextDateBtn.addEventListener('click', () => {
            const currentTopDate = this.getVisibleDate();
            const nextDay = new Date(currentTopDate);
            nextDay.setDate(nextDay.getDate() + 1);

            // Ensure rendered
            if (nextDay >= this.loadedEnd) {
                this.renderDay(nextDay, 'append');
                this.loadedEnd.setDate(this.loadedEnd.getDate() + 1);
            }
            this.scrollToTime(nextDay, 9);
            this.updateHeaderDate();
        });

        // Date Picker
        const triggerPicker = () => {
            this.hideScrollHint();
            try {
                this.elements.datePicker.focus();
                this.elements.datePicker.showPicker();
            } catch (err) {
                console.warn('showPicker not supported, falling back to click', err);
                this.elements.datePicker.click();
            }
        };

        this.elements.dateDisplay.addEventListener('click', () => {
            triggerPicker();
        });

        // Some mobile browsers respond better to touchstart for triggering native pickers
        this.elements.dateDisplay.addEventListener('touchstart', (e) => {
            // Don't preventDefault here as it might block the native label/input behavior
            triggerPicker();
        }, { passive: true });

        this.elements.datePicker.addEventListener('change', (e) => {
            if (e.target.value) {
                // Parse date as local time (append T00:00:00 to avoid UTC shift)
                const selectedDate = new Date(e.target.value + 'T00:00:00');
                this.scrollToDate(selectedDate);

                // Explicitly update header date immediately
                this.updateHeaderDate();
            }
        });

        // Back Button (Go to Calendars)
        this.elements.backBtn.addEventListener('click', () => {
            window.location.href = '../../calendars';
        });

        // Drag Selection
        const grid = this.elements.timeGrid;

        // Mouse Events
        grid.addEventListener('mousedown', (e) => this.handleStart(e));
        document.addEventListener('mousemove', (e) => this.handleMove(e));
        document.addEventListener('mouseup', () => this.handleEnd());

        // Touch Events
        grid.addEventListener('touchstart', (e) => this.handleStart(e), { passive: false });
        document.addEventListener('touchmove', (e) => this.handleMove(e), { passive: false });
        document.addEventListener('touchend', () => this.handleEnd());

        // My Bookings Toggle
        this.elements.myBookingsBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.elements.myBookingsList.classList.toggle('hidden');
        });

        // Close list when clicking outside
        document.addEventListener('click', (e) => {
            if (!this.elements.myBookingsList.contains(e.target) && e.target !== this.elements.myBookingsBtn) {
                this.elements.myBookingsList.classList.add('hidden');
            }
        });

        // Book/Delete/Update Button
        this.elements.bookBtn.addEventListener('click', () => {
            if (this.editingBooking) {
                if (this.elements.bookBtn.classList.contains('delete-btn')) {
                    this.openDeleteModal();
                } else {
                    this.openBookingModal(true); // Edit mode
                }
            } else {
                this.openBookingModal(false); // New booking
            }
        });

        // Cancel Button (Action Bar)
        this.elements.cancelBtn.addEventListener('click', () => {
            this.cancelEdit();
        });

        // Modal Listeners
        this.elements.confirmBookingBtn.addEventListener('click', () => {
            if (this.editingBooking) {
                this.updateBooking();
            } else {
                this.createBooking();
            }
        });

        this.elements.cancelBookingModal.addEventListener('click', () => this.closeModals());
        this.elements.confirmDeleteBtn.addEventListener('click', () => this.deleteBooking());
        this.elements.cancelDeleteModal.addEventListener('click', () => this.closeModals());

        // Close on background click
        this.elements.bookingModal.addEventListener('click', (e) => {
            if (e.target === this.elements.bookingModal) this.closeModals();
        });
        this.elements.deleteModal.addEventListener('click', (e) => {
            if (e.target === this.elements.deleteModal) this.closeModals();
        });
    }

    openBookingModal(isEdit) {
        this.elements.bookingModalTitle.textContent = isEdit ? 'Edit Booking' : 'Book Slot';
        this.elements.bookingDescription.value = isEdit && this.editingBooking ? this.editingBooking.description : '';
        this.elements.bookingModal.classList.remove('hidden');
        this.elements.bookingDescription.focus();
    }

    openDeleteModal() {
        this.elements.deleteModal.classList.remove('hidden');
    }

    closeModals() {
        this.elements.bookingModal.classList.add('hidden');
        this.elements.deleteModal.classList.add('hidden');
    }

    createBooking() {
        const description = this.elements.bookingDescription.value.trim() || 'No Description';
        // In real app: save to server
        const newBooking = {
            id: Math.random().toString(36).substr(2, 9),
            start: this.selection.start,
            end: this.selection.end,
            user: this.currentUser,
            description: description,
            isMine: true
        };
        this.bookings.push(newBooking);

        // Submit form
        this.submitForm('create', {
            start: this.toNaiveLocalISO(newBooking.start),
            end: this.toNaiveLocalISO(newBooking.end),
            description: newBooking.description
        });

        // Refresh View
        this.refreshView();

        this.closeModals();
        this.cancelEdit(); // Reset selection
        this.renderMyBookingsList();
    }

    cancelEdit() {
        if (!this.editingBooking) return;

        // Cancel edit mode
        document.querySelectorAll('.hidden-editing').forEach(el => el.classList.remove('hidden-editing'));
        this.editingBooking = null;
        this.selection = null;
        this.updateUI();

        // Clear handles
        document.querySelectorAll('.resize-handle').forEach(el => el.remove());
        document.querySelectorAll('.selection-label').forEach(el => el.remove());
        document.querySelectorAll('.time-slot.selected').forEach(el => el.classList.remove('selected'));
    }

    deleteBooking() {
        if (!this.editingBooking) return;

        // Remove from array
        this.bookings = this.bookings.filter(b => b.id !== this.editingBooking.id);

        // Remove DOM elements
        document.querySelectorAll(`.booking-event[data-id="${this.editingBooking.id}"]`).forEach(el => el.remove());

        // Submit form
        this.submitForm('delete', {
            id: this.editingBooking.id,
            calendar_id: this.editingBooking.calendar_id
        });

        // Reset state
        this.closeModals();
        this.cancelEdit(); // Re-use cancel logic to clear UI state
        this.renderMyBookingsList(); // Refresh list
    }

    updateBooking() {
        if (!this.editingBooking || !this.selection) return;

        // Update booking object
        this.editingBooking.start = this.selection.start;
        this.editingBooking.end = this.selection.end;
        this.editingBooking.description = this.elements.bookingDescription.value.trim() || 'No Description';

        // Submit form
        this.submitForm('update', {
            id: this.editingBooking.id,
            calendar_id: this.editingBooking.calendar_id,
            start: this.toNaiveLocalISO(this.editingBooking.start),
            end: this.toNaiveLocalISO(this.editingBooking.end),
            description: this.editingBooking.description
        });

        // Refresh View
        this.refreshView();

        // Reset state
        this.closeModals();
        this.cancelEdit();
        this.renderMyBookingsList();
    }

    renderMyBookingsList() {
        const list = this.elements.myBookingsList;
        list.innerHTML = '';

        const myBookings = this.bookings.filter(b => b.isMine);

        // Disable button if no bookings
        if (myBookings.length === 0) {
            this.elements.myBookingsBtn.disabled = true;
            this.elements.myBookingsBtn.style.opacity = '0.5';
            this.elements.myBookingsBtn.style.cursor = 'not-allowed';
        } else {
            this.elements.myBookingsBtn.disabled = false;
            this.elements.myBookingsBtn.style.opacity = '1';
            this.elements.myBookingsBtn.style.cursor = 'pointer';
        }

        // Sort by start time
        myBookings.sort((a, b) => a.start - b.start);

        if (myBookings.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'my-booking-item';
            empty.textContent = 'No upcoming bookings.';
            list.appendChild(empty);
            return;
        }

        myBookings.forEach(booking => {
            const item = document.createElement('div');
            item.className = 'my-booking-item';

            const timeStr = booking.start.toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
            });

            const timeEl = document.createElement('div');
            timeEl.className = 'my-booking-time';
            timeEl.textContent = timeStr;

            const descEl = document.createElement('div');
            descEl.className = 'my-booking-desc';
            descEl.textContent = booking.description;

            item.appendChild(timeEl);
            item.appendChild(descEl);

            item.addEventListener('click', () => {
                // Jump AND Edit
                this.jumpToBooking(booking);
                list.classList.add('hidden');

                // Trigger edit mode
                this.editingBooking = booking;
                document.querySelectorAll(`.booking-event[data-id="${booking.id}"]`).forEach(el => {
                    el.classList.add('hidden-editing');
                });
                this.updateSelection(booking.start.getTime(), booking.end.getTime() - (this.slotDuration * 60 * 1000));
            });

            list.appendChild(item);
        });
    }

    jumpToBooking(booking) {
        // Ensure the day is rendered
        const dayStart = new Date(booking.start);
        dayStart.setHours(0, 0, 0, 0);

        if (dayStart < this.loadedStart) {
            this.renderDay(dayStart, 'prepend');
            this.loadedStart = dayStart;
        } else if (dayStart >= this.loadedEnd) {
            this.renderDay(dayStart, 'append');
            const nextDay = new Date(dayStart);
            nextDay.setDate(nextDay.getDate() + 1);
            this.loadedEnd = nextDay;
        }

        // Scroll to it
        this.scrollToDate(booking.start, true);
    }

    handleInfiniteScroll() {
        const scrollArea = this.elements.scrollArea;
        const scrollTop = scrollArea.scrollTop;
        const scrollHeight = scrollArea.scrollHeight;
        const clientHeight = scrollArea.clientHeight;

        // Threshold to load more
        const threshold = 500;

        if (scrollTop < threshold) {
            // Load Previous Day
            const prevDay = new Date(this.loadedStart);
            prevDay.setDate(prevDay.getDate() - 1);

            // Save current scroll height to adjust position
            const oldScrollHeight = scrollArea.scrollHeight;

            this.renderDay(prevDay, 'prepend');
            this.loadedStart = prevDay;

            // Adjust scroll position to maintain view
            const newScrollHeight = scrollArea.scrollHeight;
            scrollArea.scrollTop += (newScrollHeight - oldScrollHeight);
        } else if (scrollTop + clientHeight > scrollHeight - threshold) {
            // Load Next Day
            const nextDay = new Date(this.loadedEnd);
            this.renderDay(nextDay, 'append');
            nextDay.setDate(nextDay.getDate() + 1);
            this.loadedEnd = nextDay;
        }
    }

    getVisibleDate() {
        // Find the day section closest to top
        const sections = document.querySelectorAll('.day-section');
        const scrollArea = this.elements.scrollArea;
        const scrollTop = scrollArea.scrollTop;

        let visibleSection = null;

        // Simple check: find first section whose bottom is > scrollTop
        for (const section of sections) {
            if (section.offsetTop + section.offsetHeight > scrollTop + 50) { // +50 for header offset
                visibleSection = section;
                break;
            }
        }

        if (visibleSection) {
            const parts = visibleSection.dataset.date.split('-');
            return new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
        }
        return new Date();
    }

    updateHeaderDate() {
        const date = this.getVisibleDate();
        const options = { weekday: 'short', month: 'short', day: 'numeric' };
        this.elements.dateDisplay.textContent = date.toLocaleDateString('en-US', options);
    }

    handleStart(e) {
        // Check for resize handle
        if (e.target.classList.contains('resize-handle')) {
            this.isResizing = true;
            const isTop = e.target.classList.contains('top');

            if (isTop) {
                // Anchor is the last slot
                this.resizeAnchor = this.selection.end.getTime() - (this.slotDuration * 60 * 1000);
            } else {
                // Anchor is the first slot
                this.resizeAnchor = this.selection.start.getTime();
            }

            return;
        }

        const slot = e.target.closest('.time-slot');
        const isSelectionClick = e.target.closest('.time-slot.selected');
        const isTimeLabel = e.target.closest('.time-label');
        const daySection = e.target.closest('.day-section');

        // Drag-to-scroll on time scale (Desktop only)
        // Check if click is on label OR in the first column of daySection
        let isLeftColumn = isTimeLabel;
        if (!isLeftColumn && daySection) {
            const rect = daySection.getBoundingClientRect();
            const x = e.clientX - rect.left;
            if (x < 100) isLeftColumn = true;
        }

        if (isLeftColumn && e.type.includes('mouse')) {
            this.isScrollDragging = true;
            this.scrollDragStartY = e.clientY;
            this.scrollDragStartScroll = this.elements.scrollArea.scrollTop;
            this.hideScrollHint();
            return;
        }

        // If clicking empty space (or slot), clear edit mode if active
        // BUT only if we are NOT clicking the current selection or a handle
        if (this.editingBooking && !e.target.closest('.resize-handle') && !isSelectionClick) {
            this.cancelEdit();
        }

        if (!slot) return;

        // If we are in edit mode and clicked the selection, don't start a new drag (for now)
        if (this.editingBooking && isSelectionClick) return;

        const time = parseInt(slot.dataset.time);

        // Prevent interaction with past slots
        if (slot.classList.contains('past-slot') || this.isSlotBooked(new Date(time))) return;

        if (e.type === 'touchstart') {
            // e.preventDefault(); 
        }

        this.isDragging = true;
        this.dragStartTime = time;
        this.updateSelection(this.dragStartTime, this.dragStartTime);
    }

    handleMove(e) {
        if (this.isScrollDragging) {
            const y = e.clientY;
            const walk = (y - this.scrollDragStartY) * 1.5; // Drag speed
            this.elements.scrollArea.scrollTop = this.scrollDragStartScroll - walk;
            return;
        }

        if (!this.isDragging && !this.isResizing) return;

        let clientX, clientY;
        if (e.type.includes('mouse')) {
            clientX = e.clientX;
            clientY = e.clientY;
        } else {
            clientX = e.touches[0].clientX;
            clientY = e.touches[0].clientY;
            e.preventDefault();
        }

        this.handleAutoScroll(clientY);

        const target = document.elementFromPoint(clientX, clientY);
        const slot = target ? target.closest('.time-slot') : null;

        if (slot) {
            const currentTime = parseInt(slot.dataset.time);
            if (this.isResizing) {
                this.updateSelection(this.resizeAnchor, currentTime);
            } else {
                this.updateSelection(this.dragStartTime, currentTime);
            }
        }
    }

    handleEnd() {
        this.isDragging = false;
        this.isResizing = false;
        this.isScrollDragging = false;
        this.dragStartTime = null;
        this.resizeAnchor = null;
        this.stopAutoScroll();
    }

    updateSelection(startTime, endTime) {
        const start = Math.min(startTime, endTime);
        const end = Math.max(startTime, endTime);

        // Check collision
        const selectionEnd = end + (this.slotDuration * 60 * 1000);

        // Check if selection overlaps with past time
        const now = Date.now();
        if (start < now) return;

        const hasCollision = this.bookings.some(b => {
            // Ignore self if editing
            if (this.editingBooking && b.id === this.editingBooking.id) return false;
            return (start < b.end && selectionEnd > b.start);
        });

        if (hasCollision) return;

        // Clear existing handles and labels
        document.querySelectorAll('.resize-handle').forEach(el => el.remove());
        document.querySelectorAll('.selection-label').forEach(el => el.remove());

        // Update Visuals
        const slots = document.querySelectorAll('.time-slot');
        let firstSlot = null;
        let lastSlot = null;

        slots.forEach(slot => {
            const time = parseInt(slot.dataset.time);
            if (time >= start && time <= end) {
                slot.classList.add('selected');
                if (!firstSlot || time < parseInt(firstSlot.dataset.time)) firstSlot = slot;
                if (!lastSlot || time > parseInt(lastSlot.dataset.time)) lastSlot = slot;
            } else {
                slot.classList.remove('selected');
            }
        });

        // Add Handles
        if (firstSlot) {
            const topHandle = document.createElement('div');
            topHandle.className = 'resize-handle top';
            firstSlot.appendChild(topHandle);

            // Add Label if Editing
            if (this.editingBooking) {
                const label = document.createElement('div');
                label.className = 'selection-label';
                label.textContent = this.editingBooking.description;
                firstSlot.appendChild(label);
            }
        }

        if (lastSlot) {
            const bottomHandle = document.createElement('div');
            bottomHandle.className = 'resize-handle bottom';
            lastSlot.appendChild(bottomHandle);
        }

        // Update Data Model
        this.selection = { start: new Date(start), end: new Date(selectionEnd) };
        this.updateUI();
    }

    handleAutoScroll(clientY) {
        const scrollArea = this.elements.scrollArea;
        const rect = scrollArea.getBoundingClientRect();
        const threshold = 50;
        const maxSpeed = 20;

        if (clientY < rect.top + threshold) {
            this.autoScrollSpeed = -maxSpeed * ((rect.top + threshold - clientY) / threshold);
        } else if (clientY > rect.bottom - threshold) {
            this.autoScrollSpeed = maxSpeed * ((clientY - (rect.bottom - threshold)) / threshold);
        } else {
            this.autoScrollSpeed = 0;
        }

        if (this.autoScrollSpeed !== 0 && !this.animationFrameId) {
            this.startAutoScroll();
        } else if (this.autoScrollSpeed === 0 && this.animationFrameId) {
            this.stopAutoScroll();
        }
    }

    startAutoScroll() {
        const scrollStep = () => {
            if (this.autoScrollSpeed !== 0) {
                this.elements.scrollArea.scrollTop += this.autoScrollSpeed;
                this.animationFrameId = requestAnimationFrame(scrollStep);
            } else {
                this.stopAutoScroll();
            }
        };
        this.animationFrameId = requestAnimationFrame(scrollStep);
    }

    stopAutoScroll() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
            this.animationFrameId = null;
        }
    }

    updateUI() {
        const btn = this.elements.bookBtn;
        const cancelBtn = this.elements.cancelBtn;

        if (this.selection) {
            const options = { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' };
            const startStr = this.selection.start.toLocaleDateString('en-US', options);
            const endStr = this.selection.end.toLocaleDateString('en-US', options);

            let displayStr = `${startStr} - ${endStr}`;
            if (this.editingBooking) {
                displayStr += ` • ${this.editingBooking.description}`;
            }

            this.elements.selectionDisplay.textContent = displayStr;
            btn.disabled = false;

            if (this.editingBooking) {
                cancelBtn.classList.remove('hidden');

                // Check if time changed
                const isSameTime = this.selection.start.getTime() === this.editingBooking.start.getTime() &&
                    this.selection.end.getTime() === this.editingBooking.end.getTime();

                if (isSameTime) {
                    btn.textContent = 'Delete Booking';
                    btn.classList.add('delete-btn');
                } else {
                    btn.textContent = 'Update Time';
                    btn.classList.remove('delete-btn');
                }
            } else {
                cancelBtn.classList.add('hidden');
                btn.textContent = 'Book Slot';
                btn.classList.remove('delete-btn');
            }

        } else {
            this.elements.selectionDisplay.textContent = 'None';
            btn.disabled = true;
            btn.textContent = 'Book Slot';
            btn.classList.remove('delete-btn');
            cancelBtn.classList.add('hidden');
        }
    }

    submitForm(action, data) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = action;

        for (const key in data) {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = key;
            input.value = data[key];
            form.appendChild(input);
        }

        document.body.appendChild(form);
        form.submit();
    }

    toNaiveLocalISO(date) {
        const pad = n => String(n).padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:00`;
    }

    refreshView() {
        // Clear and re-render the grid without re-attaching event listeners
        this.elements.timeGrid.innerHTML = '';

        // Re-render initial 3-day view (yesterday, today, tomorrow)
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);

        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);

        this.loadedStart = new Date(yesterday);
        this.loadedEnd = new Date(today);

        this.renderDay(yesterday, 'prepend');
        this.renderDay(today, 'append');
        this.renderDay(tomorrow, 'append');

        this.loadedEnd = new Date(tomorrow);
        this.loadedEnd.setDate(this.loadedEnd.getDate() + 1);

        // Update header
        this.updateHeaderDate();
    }

    hideScrollHint() {
        if (this.elements.scrollHint) {
            const elapsed = Date.now() - this.scrollHintStartTime;
            if (elapsed > 3000) { // Stay for at least 3 seconds
                this.elements.scrollHint.classList.add('hidden');
            } else {
                // If they interact before 3s, schedule the hide
                setTimeout(() => {
                    this.elements.scrollHint.classList.add('hidden');
                }, 3000 - elapsed);
            }
        }
    }

    toDateKey(date) {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new BookingControl();
});
