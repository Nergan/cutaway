// tab.js - добавляет поддержку клавиши Tab в поле ввода кода
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        const codeInput = document.getElementById('codeInput');
        if (!codeInput) {
            console.warn('codeInput not found, tab.js will not work');
            return;
        }

        codeInput.addEventListener('keydown', function(event) {
            // Проверяем, что нажата клавиша Tab без модификаторов
            if (event.key === 'Tab' && !event.ctrlKey && !event.altKey && !event.metaKey) {
                event.preventDefault(); // Предотвращаем потерю фокуса

                const start = this.selectionStart;
                const end = this.selectionEnd;
                const value = this.value;

                // Вставляем символ табуляции в позицию курсора
                // Если текст выделен, он заменяется на табуляцию
                this.value = value.substring(0, start) + '\t' + value.substring(end);

                // Возвращаем курсор после вставленного символа
                this.selectionStart = this.selectionEnd = start + 1;
            }
        });

        console.log('Toadbin tab script loaded. Tab key now inserts a tab character.');
    });
})();