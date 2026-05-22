from .base import BaseAgent


PREVIEW_HTML = {
    "promo": """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:#0c0a09;color:#fafaf9;overflow-x:hidden}
.hero{min-height:70vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:40px 20px;position:relative;background:linear-gradient(135deg,#1c0a00 0%,#2d1507 30%,#1a0a00 100%)}
.hero::before{content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;background:radial-gradient(circle at 60% 40%,rgba(249,115,22,0.12) 0%,transparent 50%);pointer-events:none}
.hero-badge{display:inline-flex;align-items:center;gap:6px;padding:6px 16px;background:rgba(249,115,22,0.12);border:1px solid rgba(249,115,22,0.25);border-radius:100px;font-size:13px;color:#fb923c;margin-bottom:24px;position:relative}
.hero h1{font-size:clamp(32px,6vw,56px);font-weight:800;line-height:1.15;margin-bottom:16px;background:linear-gradient(135deg,#fff 0%,#fdba74 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;position:relative}
.hero p{font-size:clamp(16px,2.5vw,20px);color:#a8a29e;max-width:500px;line-height:1.6;margin-bottom:36px;position:relative}
.cta-row{display:flex;gap:12px;position:relative}
.btn-primary{padding:14px 36px;background:linear-gradient(135deg,#f97316,#ea580c);border:none;border-radius:12px;color:#fff;font-size:16px;font-weight:600;cursor:pointer;box-shadow:0 4px 24px rgba(249,115,22,0.3);transition:all .2s}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(249,115,22,0.4)}
.btn-secondary{padding:14px 36px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);border-radius:12px;color:#e7e5e4;font-size:16px;cursor:pointer;transition:all .2s}
.btn-secondary:hover{background:rgba(255,255,255,0.1)}
.features{padding:60px 20px;max-width:900px;margin:0 auto}
.features h2{text-align:center;font-size:28px;margin-bottom:40px;color:#fafaf9}
.features h2 span{color:#f97316}
.feature-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px}
.feature-card{padding:28px 20px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:16px;text-align:center;transition:all .3s}
.feature-card:hover{background:rgba(249,115,22,0.06);border-color:rgba(249,115,22,0.15);transform:translateY(-4px)}
.feature-icon{font-size:36px;margin-bottom:12px}
.feature-card h3{font-size:16px;margin-bottom:8px;color:#e7e5e4}
.feature-card p{font-size:13px;color:#78716c;line-height:1.5}
.products{padding:60px 20px;background:rgba(255,255,255,0.02)}
.products-inner{max-width:900px;margin:0 auto}
.products h2{text-align:center;font-size:28px;margin-bottom:40px}
.product-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:20px}
.product-card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:16px;overflow:hidden;transition:all .3s;cursor:pointer}
.product-card:hover{border-color:rgba(249,115,22,0.3);transform:translateY(-4px)}
.product-img{height:140px;display:flex;align-items:center;justify-content:center;font-size:48px;background:linear-gradient(135deg,rgba(249,115,22,0.08),rgba(234,88,12,0.04))}
.product-info{padding:16px}
.product-info h4{font-size:15px;margin-bottom:4px}
.product-info .price{color:#f97316;font-size:18px;font-weight:700}
.product-info .old-price{color:#78716c;font-size:13px;text-decoration:line-through;margin-left:8px}
.testimonials{padding:60px 20px;max-width:700px;margin:0 auto;text-align:center}
.testimonials h2{font-size:28px;margin-bottom:40px}
.testimonial{padding:24px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:16px;margin-bottom:16px}
.testimonial p{color:#a8a29e;font-size:14px;line-height:1.6;font-style:italic}
.testimonial .author{margin-top:12px;color:#f97316;font-size:13px;font-style:normal}
footer{text-align:center;padding:40px 20px;border-top:1px solid rgba(255,255,255,0.06);color:#57534e;font-size:13px}
</style>
</head>
<body>
<section class="hero">
  <div class="hero-badge">🍦 2026 夏季限定</div>
  <h1>巧乐兹<br>一口甜蜜 满心欢喜</h1>
  <p>经典巧克力脆层包裹绵密冰淇淋，每一口都是巧克力与奶香的完美碰撞。多种口味，总有一款让你心动。</p>
  <div class="cta-row">
    <button class="btn-primary">立即尝鲜 →</button>
    <button class="btn-secondary">了解更多</button>
  </div>
</section>

<section class="features">
  <h2>为什么选择<span>巧乐兹</span>？</h2>
  <div class="feature-grid">
    <div class="feature-card">
      <div class="feature-icon">🍫</div>
      <h3>浓郁巧克力</h3>
      <p>精选西非可可豆，匠心调配的巧克力脆层，咔嚓一口，酥脆香浓</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🥛</div>
      <h3>新鲜奶源</h3>
      <p>甄选优质牧场奶源，奶香浓郁顺滑，口感细腻绵密</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">✨</div>
      <h3>多种口味</h3>
      <p>香草、草莓、抹茶、芒果……12种经典与创新口味随心选</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">❄️</div>
      <h3>极速冷链</h3>
      <p>-18°C全程冷链配送，锁住新鲜，送达手中依然完美</p>
    </div>
  </div>
</section>

<section class="products">
  <div class="products-inner">
    <h2>人气推荐</h2>
    <div class="product-grid">
      <div class="product-card">
        <div class="product-img">🍦</div>
        <div class="product-info">
          <h4>经典巧乐兹</h4>
          <span class="price">¥5</span>
        </div>
      </div>
      <div class="product-card">
        <div class="product-img">🍓</div>
        <div class="product-info">
          <h4>草莓巧乐兹</h4>
          <span class="price">¥5</span>
        </div>
      </div>
      <div class="product-card">
        <div class="product-img">🍵</div>
        <div class="product-info">
          <h4>抹茶巧乐兹</h4>
          <span class="price">¥6</span>
        </div>
      </div>
      <div class="product-card">
        <div class="product-img">🥭</div>
        <div class="product-info">
          <h4>芒果巧乐兹</h4>
          <span class="price">¥6</span>
          <span class="old-price">¥8</span>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="testimonials">
  <h2>大家都在说</h2>
  <div class="testimonial">
    <p>"夏天的第一根冰淇淋必须是巧乐兹！巧克力脆层太好吃了，每次都要囤一箱。"</p>
    <div class="author">— 小红书用户 @甜甜圈</div>
  </div>
  <div class="testimonial">
    <p>"抹茶味绝了！茶香和奶香融合得刚刚好，不会太甜，一口气能吃两根。"</p>
    <div class="author">— 大众点评用户</div>
  </div>
</section>

<footer>© 2026 巧乐兹 — 让每一口都是享受 | 伊利集团出品</footer>
</body>
</html>""",

    "login": """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0f172a;display:flex;justify-content:center;align-items:center;min-height:100vh}
.login-card{width:380px;padding:40px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:20px;backdrop-filter:blur(20px)}
.login-card h2{font-size:24px;color:#f8fafc;text-align:center;margin-bottom:8px}
.login-card .sub{text-align:center;color:#64748b;font-size:14px;margin-bottom:32px}
.field{margin-bottom:20px}
.field label{display:block;font-size:13px;color:#94a3b8;margin-bottom:6px}
.field input{width:100%;padding:12px 16px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:10px;color:#f8fafc;font-size:14px;outline:none;transition:border .2s}
.field input:focus{border-color:#6366f1}
.login-btn{width:100%;padding:14px;background:linear-gradient(135deg,#6366f1,#4f46e5);border:none;border-radius:10px;color:#fff;font-size:15px;font-weight:600;cursor:pointer;margin-top:8px;transition:all .2s}
.login-btn:hover{box-shadow:0 4px 20px rgba(99,102,241,0.3);transform:translateY(-1px)}
.divider{text-align:center;color:#475569;font-size:12px;margin:20px 0;position:relative}
.divider::before,.divider::after{content:'';position:absolute;top:50%;width:40%;height:1px;background:rgba(255,255,255,0.08)}
.divider::before{left:0}.divider::after{right:0}
.social-row{display:flex;gap:12px;justify-content:center}
.social-btn{width:44px;height:44px;border-radius:10px;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.03);display:flex;align-items:center;justify-content:center;font-size:18px;cursor:pointer;transition:all .2s}
.social-btn:hover{background:rgba(255,255,255,0.08)}
.footer-text{text-align:center;margin-top:24px;font-size:13px;color:#64748b}
.footer-text a{color:#6366f1;text-decoration:none}
</style>
</head>
<body>
<div class="login-card">
  <h2>欢迎回来 👋</h2>
  <p class="sub">登录你的账户继续</p>
  <div class="field"><label>邮箱地址</label><input placeholder="name@example.com" /></div>
  <div class="field"><label>密码</label><input type="password" placeholder="••••••••" /></div>
  <button class="login-btn">登录</button>
  <div class="divider">或</div>
  <div class="social-row">
    <div class="social-btn">G</div>
    <div class="social-btn">🐙</div>
    <div class="social-btn">📱</div>
  </div>
  <p class="footer-text">还没有账户？<a href="#">立即注册</a></p>
</div>
</body>
</html>""",

    "todo": """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#f8fafc;display:flex;justify-content:center;min-height:100vh;padding-top:60px}
.app{width:420px}
h1{font-size:28px;text-align:center;margin-bottom:24px;color:#6366f1}
.input-row{display:flex;gap:8px;margin-bottom:20px}
input{flex:1;padding:12px 16px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:10px;color:#fff;font-size:14px;outline:none}
input:focus{border-color:#6366f1}
.add-btn{padding:12px 24px;background:#6366f1;border:none;border-radius:10px;color:#fff;font-size:14px;font-weight:600;cursor:pointer}
.add-btn:hover{filter:brightness(1.1)}
.todo{display:flex;align-items:center;gap:12px;padding:14px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:10px;margin-bottom:8px;transition:all .2s}
.todo:hover{border-color:rgba(99,102,241,0.2)}
.todo.done .txt{text-decoration:line-through;opacity:.4}
.check{width:20px;height:20px;border:2px solid #6366f1;border-radius:5px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:11px;transition:all .2s}
.check.on{background:#6366f1;color:#fff}
.txt{flex:1;font-size:14px}
.del{color:#64748b;cursor:pointer;font-size:16px;opacity:0;transition:opacity .2s}
.todo:hover .del{opacity:1}
.stats{text-align:center;margin-top:20px;font-size:13px;color:#64748b}
</style>
</head>
<body>
<div class="app">
  <h1>Todo List ✅</h1>
  <div class="input-row">
    <input id="inp" placeholder="添加任务..." />
    <button class="add-btn" onclick="add()">添加</button>
  </div>
  <div id="list"></div>
  <div class="stats" id="stats"></div>
</div>
<script>
let todos=[{text:'学习 React',done:true},{text:'完成后端 API',done:false},{text:'部署上线',done:false}];
function render(){
  document.getElementById('list').innerHTML=todos.map((t,i)=>
    '<div class="todo'+(t.done?' done':'')+'">'+
    '<div class="check'+(t.done?' on':'')+'" onclick="toggle('+i+')">'+(t.done?'✓':'')+'</div>'+
    '<span class="txt">'+t.text+'</span>'+
    '<span class="del" onclick="remove('+i+')">×</span></div>'
  ).join('');
  const done=todos.filter(t=>t.done).length;
  document.getElementById('stats').textContent=done+'/'+todos.length+' 已完成';
}
function add(){const v=document.getElementById('inp');if(!v.value.trim())return;todos.push({text:v.value,done:false});v.value='';render();}
function toggle(i){todos[i].done=!todos[i].done;render();}
function remove(i){todos.splice(i,1);render();}
document.getElementById('inp').onkeydown=e=>{if(e.key==='Enter')add()};
render();
</script>
</body>
</html>""",
}


class FrontendAgent(BaseAgent):
    agent_id = "agent_frontend"
    name = "前端工程师"
    avatar = "🎨"
    role = "前端开发"
    style = "活泼，爱用 emoji"
    system_prompt = (
        "你是 AgentHub 的前端工程师，头像是🎨。你性格活泼，爱用 emoji。"
        "你擅长 HTML、CSS、JavaScript，能写出漂亮的页面。"
        "\n\n输出格式规则（必须严格遵守）："
        "\n1. 先用 [thinking]...[/thinking] 标签写 1-2 个思考块："
        "\n   [thinking]分析需求：用户需要什么类型的页面...[/thinking]"
        "\n   [thinking]设计方案：配色、布局、关键元素...[/thinking]"
        "\n2. 然后写一段简短的摘要（2-3句话），说明你做了什么。"
        "\n3. 然后输出完整的 HTML 代码（用 ```html 代码块包裹）。"
        "\n   - HTML 必须是自包含的（inline CSS + JS，不依赖外部资源）"
        "\n   - 可以直接在 iframe 中渲染"
        "\n   - 页面要美观、完整、可交互"
        "\n\n代码会自动发送到右侧面板显示和预览。摘要会在聊天框中展示。"
        "\n回复要活泼有趣，适当用 emoji。"
    )

    def _generate_reply(self, message: str, context: list = None) -> str:
        msg = message.lower()
        if any(kw in msg for kw in ["宣传", "广告", "营销", "推广", "落地页", "landing", "海报", "promo"]):
            return self._promo_reply(message)
        elif any(kw in msg for kw in ["登录", "注册", "login", "signin", "signup"]):
            return self._login_reply()
        elif any(kw in msg for kw in ["bug", "报错", "问题", "修复"]):
            return "让我看看 👀 嗯找到问题了！是 CSS 层级的问题，已经修复了 ✅ 加了个 z-index 就搞定了～"
        elif any(kw in msg for kw in ["谢谢", "感谢", "不错"]):
            return "哈哈不客气！有前端需求随时找我，写 UI 我最在行了 💪✨"
        return self._code_reply()

    def _promo_reply(self, message: str) -> str:
        return (
            "[thinking]分析需求：用户需要巧乐兹冰淇淋的营销宣传页面，需要品牌展示和产品推荐[/thinking]"
            "[thinking]设计方案：深色背景+橙色渐变配色，突出巧克力甜蜜感，包含Hero区、卖点、商品、评价四个模块[/thinking]"
            "巧乐兹宣传页搞定！🍦 给你写了个完整的营销落地页，右侧面板可以直接预览效果～\n\n"
            "```html\n" + PREVIEW_HTML["promo"] + "\n```"
        )

    def _login_reply(self) -> str:
        return (
            "[thinking]分析需求：用户需要一个登录页面，要求简约大气[/thinking]"
            "[thinking]设计方案：毛玻璃卡片风格，渐变按钮，社交登录选项[/thinking]"
            "登录页搞定啦！✨ 毛玻璃风格 + 渐变按钮，简约大气\n\n"
            "```html\n" + PREVIEW_HTML["login"] + "\n```"
        )

    def _code_reply(self) -> str:
        return (
            "[thinking]分析需求：用户需要一个 Todo 组件，带基本的增删改查功能[/thinking]"
            "[thinking]设计方案：暗色主题，勾选删除计数，简洁交互[/thinking]"
            "搞定！给你写了个 Todo 组件 ✨ 带勾选、删除、计数功能\n\n"
            "```html\n" + PREVIEW_HTML["todo"] + "\n```"
        )
