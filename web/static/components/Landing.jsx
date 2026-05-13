// Landing page — with trust/fear-closing sections
const { useState: useLandingState } = React;

const SERVICES_PREVIEW = [
{ abbr: 'ПФ',  name: 'Авито ПФ',     desc: 'Просмотры, лайки, запросы контактов — поведенческие факторы', price: 'от 6 ₽/ПФ', available: true },
{ abbr: 'ОТЗ', name: 'Отзывы',        desc: 'Накрутка и удаление: Авито, ВКонтакте, Яндекс, 2ГИС, Google', price: 'по тарифу', available: true },
{ abbr: 'ЯПФ', name: 'Яндекс ПФ',    desc: 'Поведенческие факторы для Яндекса — продвижение в поиске', price: null, badge: 'Скоро', available: false },
{ abbr: 'SEO', name: 'SEO-буст',      desc: 'Ссылочное продвижение, рост позиций в поиске', price: null, badge: 'Скоро', available: false },
{ abbr: 'КП',  name: 'Копирайтинг',  desc: 'Тексты для объявлений, карточек товара, описаний', price: null, badge: 'Скоро', available: false },
{ abbr: 'SMM', name: 'SMM',           desc: 'Ведение соцсетей и создание контента', price: null, badge: 'Скоро', available: false }];


const FAQS = [
{
  q: 'Могут ли заблокировать объявление или аккаунт?',
  a: 'За 3 года работы — ни одного прецедента бана. Авито зарабатывает на каждом просмотре по тарифу «оплата за просмотры», поэтому блокировать за это коммерчески бессмысленно. Наши действия неотличимы от обычного органического трафика: мы находим объявление через поиск, а не переходим по прямой ссылке.'
},
{
  q: 'Как быстро появится результат?',
  a: 'Первые просмотры начинают поступать с первого рабочего дня. Рост позиций обычно заметен через 3–7 дней непрерывной работы. На новых объявлениях эффект быстрее.'
},
{
  q: 'А что если результата не будет?',
  a: 'Мы работаем с реальным трафиком, а не ботами, поэтому просмотры гарантированы — они отображаются в статистике Авито. Если по каким-то причинам заказ не был выполнен, средства возвращаются на баланс.'
},
{
  q: 'Это реальные люди или боты?',
  a: 'Только реальные устройства. Аудитория находит объявление через поиск по целевым запросам, просматривает 2–10 минут, изучает фото. Такое поведение алгоритм не может отличить от органики.'
},
{
  q: 'Сколько просмотров нужно?',
  a: 'Хватит и 15 ПФ в сутки, главное — непрерывность. Есть клиенты, которых мы ведём уже 3+ года без остановки. Резкое увеличение объёмов лучше делать постепенно.'
},
{
  q: 'Как пополнить баланс?',
  a: 'Автоматически через ЮКассу: банковская карта, СБП, электронные кошельки. Или вручную через менеджера в Telegram — для юр. лиц и безналичной оплаты.'
}];


function FaqItem({ q, a }) {
  const [open, setOpen] = useLandingState(false);
  return (
    <div
      style={{
        borderBottom: '1px solid var(--border)',
        cursor: 'pointer'
      }}
      onClick={() => setOpen((v) => !v)}>
      
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '16px 0', gap: 16
      }}>
        <span style={{ fontWeight: 600, fontSize: '0.9375rem', color: 'var(--text-1)', lineHeight: 1.4 }}>{q}</span>
        <span style={{
          flexShrink: 0, width: 24, height: 24, borderRadius: '50%',
          background: open ? 'var(--primary)' : 'var(--surface-2)',
          border: '1.5px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '0.75rem', color: open ? '#fff' : 'var(--text-3)',
          transition: 'background 0.2s, color 0.2s'
        }}>
          {open ? '▲' : '▼'}
        </span>
      </div>
      {open &&
      <div style={{ fontSize: '0.875rem', color: 'var(--text-2)', lineHeight: 1.7, paddingBottom: 16 }}>
          {a}
        </div>
      }
    </div>);

}

const LandingPage = ({ onNavigate, brandName }) => {
  return (
    <div className="page-wrap">

      {/* Hero */}
      <section className="landing-hero">
        <div className="landing-hero__eyebrow">Платформа цифрового продвижения</div>
        <h1 className="landing-hero__headline">
          Продвигайте бизнес<br />с одного личного кабинета
        </h1>
        <p className="landing-hero__sub">
          Поведенческие факторы, отзывы, SEO — все услуги на одном балансе.
          Заказ в 3 клика, результат за 24 часа.
        </p>
        <div className="landing-hero__ctas">
          <button className="btn btn--primary btn--lg" onClick={() => onNavigate('login-tg')}>
            Войти через Telegram
          </button>
          <button className="btn btn--ghost btn--lg" onClick={() => onNavigate('login')}>
            Войти через Email
          </button>
        </div>
        <p style={{ marginTop: 16, fontSize: '0.8125rem', color: 'var(--text-3)' }}>
          Нет аккаунта?{' '}
          <span style={{ color: 'var(--primary)', fontWeight: 600, cursor: 'pointer' }} onClick={() => onNavigate('register')}>
            Зарегистрироваться
          </span>
        </p>
      </section>

      {/* Stats */}
      <div style={{ padding: '0 20px' }}>
        <div className="container">
          <div className="landing-stats-grid" style={{
            display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12,
            margin: '0 auto', padding: '32px 0'
          }}>
            {[
            { num: '50 000+', label: 'Выполненных заказов', color: '#0088cc' },
            { num: '98%',     label: 'Довольных клиентов',  color: '#0088cc' },
            { num: '3 года',  label: 'На рынке',            color: '#0088cc' }].
            map((s, i) =>
            <div
              key={i}
              className="card"
              style={{
                padding: '24px 20px', textAlign: 'center', cursor: 'default',
                transition: 'transform 0.2s, box-shadow 0.2s',
                borderTop: '3px solid rgb(0, 136, 204)',
                borderRightColor: 'rgb(0, 136, 204)',
                borderBottomColor: 'rgb(0, 136, 204)',
                borderLeftColor: 'rgb(0, 136, 204)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-4px)';
                e.currentTarget.style.boxShadow = '0 12px 32px rgba(0,0,0,0.10), 0 4px 12px rgba(0,136,204,0.18)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.boxShadow = '';
              }}>
                <div style={{
                  fontSize: 'clamp(1.5rem, 3vw, 2rem)', fontWeight: 800,
                  color: 'rgb(0, 136, 204)', letterSpacing: '-0.04em', lineHeight: 1, marginBottom: 8,
                }}>{s.num}</div>
                <div style={{ fontSize: '0.8125rem', color: 'var(--text-2)', lineHeight: 1.4 }}>{s.label}</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Services */}
      <section className="landing-services" id="services">
        <div className="container">
          <h2 className="landing-services__title">Каталог услуг</h2>
          <div className="services-grid">
            {SERVICES_PREVIEW.map((s, i) =>
            <div
              key={i}
              className={`card service-card card--hover${!s.available ? ' service-card--disabled' : ''}`}
              onClick={() => s.available && onNavigate('login')}>
              
                <div style={{ width: 38, height: 38, borderRadius: 8, background: s.available ? 'var(--primary-dim)' : 'var(--surface-3)', color: s.available ? 'var(--primary)' : 'var(--text-3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem', fontWeight: 800 }}>{s.abbr}</div>
                <div className="service-card__name">{s.name}</div>
                <div className="service-card__desc">{s.desc}</div>
                <div className="service-card__footer">
                  {s.available ?
                <span className="service-card__price">{s.price}</span> :
                <span className="badge badge--muted">{s.badge}</span>
                }
                  {s.available && <span style={{ fontSize: '0.75rem', color: 'var(--primary)', fontWeight: 600 }}>Заказать →</span>}
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="landing-how">
        <div className="container">
          <h2 style={{ textAlign: 'center', marginBottom: 8 }}>Как это работает</h2>
          <p style={{ textAlign: 'center', color: 'var(--text-2)', fontSize: '0.9rem', marginBottom: 32 }}>Три шага до результата</p>
          <div className="how-steps">
            {[
            { n: '1', t: 'Пополните баланс', d: 'Через ЮКассу автоматически или вручную через менеджера. Средства зачисляются моментально.' },
            { n: '2', t: 'Выберите услугу', d: 'Откройте каталог, выберите нужную услугу и настройте параметры — ссылки, дни, объём.' },
            { n: '3', t: 'Отслеживайте результат', d: 'Заказ отображается в личном кабинете. При смене статуса — уведомление в Telegram.' }].
            map((s) =>
            <div key={s.n} className="how-step">
                <div className="how-step__num">{s.n}</div>
                <div className="how-step__title">{s.t}</div>
                <div className="how-step__desc">{s.d}</div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Trust / закрытие страхов */}
      <section style={{ padding: '60px 0', background: 'var(--surface)', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
        <div className="container">
          <h2 style={{ textAlign: 'center', marginBottom: 8 }}>Почему нам доверяют</h2>
          <p style={{ textAlign: 'center', color: 'var(--text-2)', fontSize: '0.9rem', marginBottom: 40 }}>
            Мы работаем с 2023 года. Вот ответы на главные страхи
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16 }}>
            {[
            {
              title: 'Нет банов за 3 года',
              desc: 'Ни один из тысяч клиентов не получил блокировку. Авито зарабатывает на каждом просмотре — блокировать за это нелогично.'
            },
            {
              title: 'Реальные люди, не боты',
              desc: 'Трафик с настоящих устройств. Объявление находят через поиск по целевым запросам — алгоритм видит это как органику.'
            },
            {
              title: 'Возврат за невыполненные заказы',
              desc: 'Если что-то пошло не так — средства возвращаются на баланс. Никаких споров и разногласий.'
            },
            {
              title: 'Прозрачная статистика',
              desc: 'Просмотры отображаются в вашей статистике Авито в реальном времени. Вы видите каждый выполненный ПФ.'
            },
            {
              title: 'Быстрый старт',
              desc: 'Заказ запускается на следующий день. Первые просмотры — в течение нескольких часов после запуска.'
            },
            {
              title: 'Поддержка в Telegram',
              desc: 'Команда отвечает быстро. Если возник вопрос по заказу — решим без бюрократии напрямую в чате.'
            }].
            map((item, i) =>
            <div key={i} className="card" style={{ padding: '20px 22px', display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                <div style={{ width: 32, height: 32, borderRadius: 8, flexShrink: 0, background: 'var(--primary-dim)', color: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 800 }}>{i + 1}</div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: '0.9375rem', marginBottom: 5 }}>{item.title}</div>
                  <div style={{ fontSize: '0.8125rem', color: 'var(--text-2)', lineHeight: 1.6 }}>{item.desc}</div>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" style={{ padding: '60px 0' }}>
        <div className="container" style={{ maxWidth: 720 }}>
          <h2 style={{ textAlign: 'center', marginBottom: 8 }}>Частые вопросы</h2>
          <p style={{ textAlign: 'center', color: 'var(--text-2)', fontSize: '0.9rem', marginBottom: 36 }}>
            Ответы на то, что волнует перед первым заказом
          </p>
          <div className="card" style={{ padding: '8px 28px' }}>
            {FAQS.map((f, i) => <FaqItem key={i} q={f.q} a={f.a} />)}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="landing-cta" style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="card" style={{ maxWidth: 560, margin: '0 auto', padding: '40px 32px', textAlign: 'center', borderTop: '3px solid var(--primary)' }}>
            <h2 style={{ marginBottom: 12 }}>Готовы начать?</h2>
            <p style={{ color: 'var(--text-2)', marginBottom: 28, fontSize: '0.9rem' }}>
              Создайте аккаунт за 30 секунд через Telegram — без пароля и email.
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
              <button className="btn btn--primary btn--lg" onClick={() => onNavigate('login-tg')}>
                Войти через Telegram
              </button>
              <button className="btn btn--ghost btn--lg" onClick={() => onNavigate('register')}>
                Email-регистрация
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Contacts */}
      <section id="contacts" style={{ padding: '60px 0', background: 'var(--surface)', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
        <div className="container" style={{ maxWidth: 760 }}>
          <h2 style={{ textAlign: 'center', marginBottom: 8 }}>Контакты</h2>
          <p style={{ textAlign: 'center', color: 'var(--text-2)', fontSize: '0.9rem', marginBottom: 36 }}>
            Свяжитесь удобным способом — отвечаем в течение рабочего дня
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
            {[
              { label: 'Поддержка', desc: '@avito_pf_otzizi', href: 'https://t.me/avito_pf_otzizi', icon: '💬', primary: true },
              { label: 'Бот для заказа', desc: '@AVITOPF_bot', href: 'https://t.me/AVITOPF_bot', icon: '🤖' },
              { label: 'Telegram-канал', desc: '@pf_avito_top', href: 'https://t.me/pf_avito_top', icon: '📣' },
            ].map((c, i) => (
              <a
                key={i}
                href={c.href}
                target="_blank"
                rel="noopener"
                className="card card--hover"
                style={{
                  padding: '24px 22px',
                  textDecoration: 'none',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  textAlign: 'center',
                  gap: 8,
                  borderTop: c.primary ? '3px solid var(--primary)' : undefined,
                }}
              >
                <div style={{
                  width: 48, height: 48, borderRadius: 12,
                  background: 'var(--primary-dim)', color: 'var(--primary)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '1.5rem',
                }}>{c.icon}</div>
                <div style={{ fontWeight: 700, fontSize: '0.9375rem', color: 'var(--text-1)' }}>{c.label}</div>
                <div style={{ fontSize: '0.875rem', color: 'var(--primary)', fontWeight: 600 }}>{c.desc}</div>
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="landing-footer">
        <div className="landing-footer__links">
          <a href="https://t.me/pf_avito_top" target="_blank" rel="noopener">Telegram-канал</a>
          <a href="https://t.me/AVITOPF_bot" target="_blank" rel="noopener">Бот для заказа</a>
          <a href="https://t.me/avito_pf_otzizi" target="_blank" rel="noopener">Поддержка</a>
        </div>
        <div className="landing-footer__copy">© 2026 {brandName}. Все права защищены.</div>
      </footer>
    </div>);

};

Object.assign(window, { LandingPage });