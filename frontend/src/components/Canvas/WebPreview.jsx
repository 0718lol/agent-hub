import React, { useState } from 'react'

const DEMO_HTML = `<!DOCTYPE html>
<html>
<head>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Inter', sans-serif; background: #0f172a; color: #f8fafc; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
  .container { max-width: 400px; width: 100%; padding: 20px; }
  h1 { font-size: 24px; margin-bottom: 20px; text-align: center; color: #6366f1; }
  .input-row { display: flex; gap: 8px; margin-bottom: 16px; }
  input { flex: 1; padding: 10px 14px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; color: white; font-size: 14px; outline: none; }
  input:focus { border-color: #6366f1; }
  button { padding: 10px 20px; background: #6366f1; border: none; border-radius: 8px; color: white; font-size: 14px; cursor: pointer; }
  button:hover { filter: brightness(1.1); }
  .todo-item { display: flex; align-items: center; gap: 12px; padding: 12px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; margin-bottom: 8px; }
  .todo-item.done .text { text-decoration: line-through; opacity: 0.5; }
  .checkbox { width: 18px; height: 18px; border: 2px solid #6366f1; border-radius: 4px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
  .checkbox.checked { background: #6366f1; }
  .text { flex: 1; font-size: 14px; }
</style>
</head>
<body>
<div class="container">
  <h1>Todo App</h1>
  <div class="input-row">
    <input id="input" placeholder="添加任务..." />
    <button onclick="addTodo()">添加</button>
  </div>
  <div id="list"></div>
</div>
<script>
let todos = [];
function render() {
  const list = document.getElementById('list');
  list.innerHTML = todos.map((t, i) =>
    '<div class="todo-item ' + (t.done ? 'done' : '') + '">' +
    '<div class="checkbox ' + (t.done ? 'checked' : '') + '" onclick="toggle(' + i + ')">' + (t.done ? '✓' : '') + '</div>' +
    '<span class="text">' + t.text + '</span>' +
    '</div>'
  ).join('');
}
function addTodo() {
  const input = document.getElementById('input');
  if (!input.value.trim()) return;
  todos.push({ text: input.value, done: false });
  input.value = '';
  render();
}
function toggle(i) { todos[i].done = !todos[i].done; render(); }
document.getElementById('input').addEventListener('keydown', e => { if (e.key === 'Enter') addTodo(); });
render();
</script>
</body>
</html>`

export default function WebPreview() {
  const [url] = useState('http://localhost:3000/preview')

  return (
    <div className="web-preview">
      <div className="preview-url-bar">
        <span style={{ color: '#10b981', fontSize: 12 }}>●</span>
        <input value={url} readOnly />
      </div>
      <iframe
        className="preview-iframe"
        srcDoc={DEMO_HTML}
        sandbox="allow-scripts"
        title="Preview"
      />
    </div>
  )
}
