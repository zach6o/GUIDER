import { useState } from 'react';
import type { Plan, StepEdit } from './types';
import './settings.css';

export function PlanEditor({ plan, disabled, onSave }: {
  plan: Plan; disabled: boolean; onSave: (steps: StepEdit[]) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [steps, setSteps] = useState<StepEdit[]>([]);
  function edit(index: number, field: keyof Omit<StepEdit, 'id'>, value: string) {
    setSteps(current => current.map((step, at) => at === index ? { ...step, [field]: value } : step));
  }
  function move(index: number, direction: number) {
    setSteps(current => {
      const next = [...current];
      [next[index], next[index + direction]] = [next[index + direction], next[index]];
      return next;
    });
  }
  if (!open) return <button className="text-button" disabled={disabled} onClick={() => {
    setSteps(plan.steps.map(({ id, title, action, expected_result, success_criterion }) =>
      ({ id, title, action, expected_result, success_criterion })));
    setOpen(true);
  }}>Edit or reorder steps</button>;
  return <form className="plan-editor" aria-label="Edit plan" onSubmit={event => {
    event.preventDefault(); void onSave(steps).then(() => setOpen(false)).catch(() => {});
  }}>
    <p>Saving creates a new version that you must confirm before starting.</p>
    {steps.map((step, index) => <fieldset key={step.id} disabled={disabled}>
      <legend>Step {index + 1}</legend>
      <label>Title<input required maxLength={120} value={step.title} onChange={event => edit(index, 'title', event.target.value)} /></label>
      <label>Action<textarea required maxLength={1000} value={step.action} onChange={event => edit(index, 'action', event.target.value)} /></label>
      <label>Expected result<textarea maxLength={500} value={step.expected_result} onChange={event => edit(index, 'expected_result', event.target.value)} /></label>
      <label>Success criterion<textarea required maxLength={500} value={step.success_criterion} onChange={event => edit(index, 'success_criterion', event.target.value)} /></label>
      <div className="plan-buttons">
        <button type="button" className="text-button" disabled={index === 0} onClick={() => move(index, -1)} aria-label={`Move step ${index + 1} up`}>Move up</button>
        <button type="button" className="text-button" disabled={index === steps.length - 1} onClick={() => move(index, 1)} aria-label={`Move step ${index + 1} down`}>Move down</button>
      </div>
    </fieldset>)}
    <div className="plan-buttons"><button className="primary" disabled={disabled}>Save revised plan</button>
      <button type="button" className="text-button" disabled={disabled} onClick={() => setOpen(false)}>Cancel editing</button></div>
  </form>;
}
