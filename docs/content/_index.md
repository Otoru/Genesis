---
title: Redirecting
---

<script>
    var path = window.location.pathname;
    if (path.endsWith('/')) {
        window.location.href = path + 'docs/';
    } else {
        window.location.href = path + '/docs/';
    }
</script>
