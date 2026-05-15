(function () {
  function hide(img) {
    img.dataset.imgGuard = "broken";
    img.style.display = "none";
    var parent = img.parentElement;
    if (parent) parent.classList.add("img-broken");
  }

  function check(img) {
    if (img.complete && img.naturalWidth === 0 && img.src && img.src.indexOf("data:") !== 0) {
      hide(img);
    }
  }

  function wire(img) {
    if (img.dataset.imgGuardWired) return;
    img.dataset.imgGuardWired = "1";
    img.addEventListener("error", function () { hide(img); }, { once: true });
    if (img.complete) check(img);
  }

  function scan() {
    var imgs = document.getElementsByTagName("img");
    for (var i = 0; i < imgs.length; i++) wire(imgs[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scan);
  } else {
    scan();
  }
  window.addEventListener("load", scan);
})();
