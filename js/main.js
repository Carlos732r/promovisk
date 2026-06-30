// ===== PROMOVISK - JAVASCRIPT =====

// ── Mobile Menu ──────────────────────────────────────────────
const hamburger = document.getElementById('hamburger');
const mobileMenu = document.getElementById('mobile-menu');
if (hamburger && mobileMenu) {
  hamburger.addEventListener('click', () => mobileMenu.classList.toggle('aberto'));
}

// ── Scroll shadow no header ───────────────────────────────────
window.addEventListener('scroll', () => {
  const header = document.querySelector('header');
  if (header) header.style.boxShadow = window.scrollY > 10 ? '0 2px 20px rgba(0,0,0,0.4)' : 'none';
});

// ── Newsletter ────────────────────────────────────────────────
const newsletterForm = document.getElementById('newsletter-form');
if (newsletterForm) {
  newsletterForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const email = newsletterForm.querySelector('input[type="email"]').value;
    if (email) {
      alert('✅ Ótimo! Você vai receber as melhores promoções no seu e-mail.');
      newsletterForm.reset();
    }
  });
}

// ── Utilitários ───────────────────────────────────────────────
function formatarPreco(valor) {
  return valor.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function calcularDesconto(original, atual) {
  return Math.round(((original - atual) / original) * 100);
}

// ── Renderizar card de produto ────────────────────────────────
function criarCardProduto(p) {
  const desconto = p.desconto_porcentagem || calcularDesconto(p.preco_original, p.preco_atual);
  const frete    = p.frete_gratis ? '<span class="badge-frete">Frete Grátis ⚡</span>' : '';
  const parcelas = p.parcelas_num && p.parcelas_valor
    ? `<div class="preco-parcelado">${p.parcelas_num}x ${formatarPreco(p.parcelas_valor)} sem juros</div>`
    : '';
  const precoRiscado = p.preco_original > p.preco_atual
    ? `<div class="preco-antigo">${formatarPreco(p.preco_original)}</div>`
    : '';
  const cupom = p.cupom_codigo
    ? `<div class="card-cupom">🏷️ Cupom: <span class="cupom-codigo">${p.cupom_codigo}</span>${p.cupom_valor ? ' (' + p.cupom_valor + ' off)' : ''}</div>`
    : '';

  return `
    <a href="${p.link_afiliado}" class="card-produto" target="_blank" rel="noopener sponsored">
      <div class="card-img">
        <span class="badge-desconto">${desconto}% OFF</span>
        ${frete}
        <img
          src="${p.imagem}"
          alt="${p.titulo}"
          onerror="this.src='https://via.placeholder.com/130x130/1A2E42/F5A623?text=${encodeURIComponent(p.categoria_emoji || '🛍️')}';"
          loading="lazy"
        />
      </div>
      <div class="card-corpo">
        <div class="card-categoria">${p.categoria_emoji || ''} ${p.categoria}</div>
        <div class="card-nome">${p.titulo}</div>
        <div class="card-precos">
          ${precoRiscado}
          <div class="preco-atual">${formatarPreco(p.preco_atual)}</div>
          ${parcelas}
        </div>
        ${cupom}
        <div class="btn-comprar">Ver oferta no ${p.loja}</div>
      </div>
    </a>`;
}

// ── Renderizar card destaque ──────────────────────────────────
function criarCardDestaque(p) {
  return `
    <a href="${p.link_afiliado}" class="card-destaque" target="_blank" rel="noopener sponsored">
      <img
        src="${p.imagem}"
        alt="${p.titulo}"
        onerror="this.src='https://via.placeholder.com/90x90/1A2E42/F5A623?text=${encodeURIComponent(p.categoria_emoji || '🛍️')}';"
        loading="lazy"
      />
      <div class="destaque-info">
        <div class="card-categoria">${p.categoria_emoji || ''} ${p.categoria}</div>
        <div class="card-nome">${p.titulo}</div>
        <div class="preco-antigo">${formatarPreco(p.preco_original)}</div>
        <div class="preco-atual">${formatarPreco(p.preco_atual)}</div>
        ${p.parcelas_num ? `<div class="preco-parcelado">${p.parcelas_num}x ${formatarPreco(p.parcelas_valor)} sem juros</div>` : ''}
      </div>
    </a>`;
}

// ── Carregar promoções do JSON ────────────────────────────────
async function carregarPromocoes() {
  // Descobre a raiz do site (funciona tanto em index.html quanto em subpastas)
  const base = document.documentElement.dataset.base || '';
  const url  = `${base}/data/promocoes.json`;

  try {
    const res  = document.getElementById('grid-destaques') ||
                 document.getElementById('grid-promocoes');
    if (!res) return; // página sem grid, não precisa carregar

    const resp = await fetch(url);
    if (!resp.ok) throw new Error('Arquivo não encontrado');
    const dados = await resp.json();

    renderizarPagina(dados);
    atualizarTimestamp(dados.atualizado_em);

  } catch (err) {
    console.warn('PromoVisk: não foi possível carregar promocoes.json', err);
  }
}

function renderizarPagina(dados) {
  const { promocoes } = dados;

  // Grid de destaques (index.html)
  const gridDestaques = document.getElementById('grid-destaques');
  if (gridDestaques) {
    const destaques = promocoes.filter(p => p.destaque).slice(0, 3);
    const resto     = promocoes.filter(p => !p.destaque);
    // Se não tiver destaque marcado, usa os 3 primeiros
    const itens = destaques.length ? destaques : promocoes.slice(0, 3);
    gridDestaques.innerHTML = itens.map(criarCardDestaque).join('');
  }

  // Grid principal de cards (index.html e promocoes.html)
  const gridPrincipal = document.getElementById('grid-promocoes');
  if (gridPrincipal) {
    // Na index mostra até 6; na página de promoções mostra tudo
    const isPaginaPromocoes = window.location.pathname.includes('promocoes');
    const itens = isPaginaPromocoes ? promocoes : promocoes.slice(0, 6);
    gridPrincipal.innerHTML = itens.map(criarCardProduto).join('');
  }

  // Contador de ofertas ativas
  const contador = document.getElementById('contador-ofertas');
  if (contador) contador.textContent = dados.total || promocoes.length;
}

function atualizarTimestamp(dataISO) {
  const el = document.getElementById('ultima-atualizacao');
  if (!el || !dataISO) return;
  const d = new Date(dataISO);
  el.textContent = d.toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

// ── Filtros na página de promoções ───────────────────────────
function iniciarFiltros() {
  document.querySelectorAll('.filtro-chip').forEach(btn => {
    btn.addEventListener('click', async () => {
      document.querySelectorAll('.filtro-chip').forEach(b => b.classList.remove('ativo'));
      btn.classList.add('ativo');

      const categoria = btn.dataset.categoria || 'todos';
      const base = document.documentElement.dataset.base || '';
      const resp = await fetch(`${base}/data/promocoes.json`);
      const dados = await resp.json();

      const grid = document.getElementById('grid-promocoes');
      if (!grid) return;

      const filtradas = categoria === 'todos'
        ? dados.promocoes
        : dados.promocoes.filter(p =>
            p.categoria.toLowerCase().includes(categoria.toLowerCase()));

      grid.innerHTML = filtradas.length
        ? filtradas.map(criarCardProduto).join('')
        : '<p style="color:var(--cinza-texto);grid-column:1/-1;text-align:center;padding:40px 0">Nenhuma promoção nessa categoria no momento.</p>';
    });
  });
}

// ── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  carregarPromocoes();
  iniciarFiltros();
});
