document.addEventListener("DOMContentLoaded", function () {
    const sidebarLinks = document.querySelectorAll(".nav-link");
    const sidebar = document.getElementById("sidebar");
    const content = document.getElementById("content");
    const sidebarCollapse = document.getElementById("sidebarCollapse");

    sidebarCollapse.addEventListener("click", function () {
        toggleSidebar();
    });

    sidebarLinks.forEach(function (link) {
        link.addEventListener("click", function (event) {
            event.preventDefault();
            sidebarLinks.forEach(function (otherLink) {
                otherLink.classList.remove("active");
            });
            link.classList.add("active");
            const sectionId = link.getAttribute("href").substring(1);
            loadSection(sectionId);
        });
    });

    function loadSection(sectionId) {
        const contentSection = document.getElementById(`${sectionId}-content`);
        if (contentSection) {
            document.querySelectorAll(".content-section").forEach(function (section) {
                section.style.display = "none";
            });
            contentSection.style.display = "block";
        } else {
            console.error(`Section with id '${sectionId}-content' not found`);
        }
    }

    function toggleSidebar() {
        sidebar.classList.toggle("active");
        content.classList.toggle("active");
    }
});
