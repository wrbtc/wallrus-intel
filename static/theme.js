(function(){
    var t=localStorage.getItem('theme');
    if(t){document.documentElement.setAttribute('data-theme',t)}
    update();
    function update(){
        var d=document.documentElement.getAttribute('data-theme');
        var b=document.querySelector('.theme-toggle');
        if(b){
            if(d==='light')b.textContent='light';
            else if(d==='dark')b.textContent='dark';
            else b.textContent=window.matchMedia('(prefers-color-scheme:light)').matches?'light':'dark';
        }
    }
    window.toggleTheme=function(){
        var d=document.documentElement.getAttribute('data-theme');
        var current=d||(window.matchMedia('(prefers-color-scheme:light)').matches?'light':'dark');
        var next=current==='dark'?'light':'dark';
        document.documentElement.setAttribute('data-theme',next);
        localStorage.setItem('theme',next);
        update();
    };
})();
