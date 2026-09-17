import type { FormEvent } from 'react';
import type { HistoryFilters as Filters } from './types';
import './settings.css';

export function HistoryFilters({ onChange, disabled }: { onChange: (filters: Filters) => void; disabled: boolean }) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const start = String(data.get('since') || ''), end = String(data.get('until') || '');
    onChange({ q: String(data.get('q') || ''), outcome: String(data.get('outcome') || ''),
      since: start ? new Date(`${start}T00:00:00`).toISOString() : undefined,
      until: end ? new Date(`${end}T23:59:59.999`).toISOString() : undefined });
  }
  return <form className="history-filters" onSubmit={submit} onReset={() => onChange({})}>
    <label>Search your tasks<input name="q" type="search" maxLength={120} /></label>
    <label>Outcome<select name="outcome"><option value="">Any outcome</option>
      <option value="achieved">Verified complete</option><option value="user_reported">You reported complete</option>
      <option value="stopped">Stopped</option><option value="failed">Failed</option><option value="expired">Expired</option>
    </select></label>
    <label>From<input name="since" type="date" /></label><label>Through<input name="until" type="date" /></label>
    <button className="primary" disabled={disabled}>Search history</button>
    <button type="reset" className="text-button" disabled={disabled}>Clear filters</button>
  </form>;
}
