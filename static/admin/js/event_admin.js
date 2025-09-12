document.addEventListener('DOMContentLoaded', function() {
    const rulesType = document.querySelector('#id_rules_type');
    const rulesTextRow = document.querySelector('.field-rules_text');
    const rulesFileRow = document.querySelector('.field-rules_file');

    function toggleRulesFields() {
        if (rulesType.value === 'TEXT') {
            rulesTextRow.style.display = 'block';
            rulesFileRow.style.display = 'none';
        } else if (rulesType.value === 'IMAGE' || rulesType.value === 'PDF') {
            rulesTextRow.style.display = 'none';
            rulesFileRow.style.display = 'block';
        } else {
            rulesTextRow.style.display = 'none';
            rulesFileRow.style.display = 'none';
        }
    }

    // Initial toggle
    toggleRulesFields();

    // Toggle on change
    rulesType.addEventListener('change', toggleRulesFields);
});
