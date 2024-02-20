$(document).ready(function () {
    const currentSection = window.location.hash.substring(1);

    if (currentSection) {
        showContent(currentSection);
    } else {
        showContent('homeSection');
    }

    $('.nav-link').click(function () {
        $('.nav-link').removeClass('active'); // Удаляем класс у всех элементов
        $(this).addClass('active'); 
    });
});

function showContent(sectionId) {
    window.location.hash = '#' + sectionId;

    $('.nav-link').removeClass('active');
    $('[href="#' + sectionId + '"]').addClass('active');

    $('.section-content').addClass('hidden');
    $('#' + sectionId).removeClass('hidden');
}

function toggleSubMenu(subMenuId) {
    $('#' + subMenuId).toggleClass('hidden');
    $('.main-content').toggleClass('main-content-shifted');
}
