/**
 * The character sheet: who you are, and what you are wearing.
 *
 * The numbers here are the ones the server actually simulates with, taken from the
 * inventory packet rather than reconstructed. That distinction matters more than it
 * sounds: vitals travel as a fraction of a maximum the client never sees, so a sheet
 * that derived the maximum from the class would quietly disagree with the server
 * about what a helm was worth, and disagree by more with every level.
 *
 * A panel rather than a modal, deliberately. The compose dialog takes the screen
 * because it asks a question that cannot be answered while walking; this one is read
 * while walking, and a full-screen sheet in a game with no pause is a way to get
 * killed by something you could not see.
 */

import type { ClassInfo, EquipmentSlotInfo, ItemInfo } from './api'
import type { Loadout } from '../net/session'

export interface CharacterSheetProps {
  name: string
  characterClass: ClassInfo
  level: number
  experience: number
  nextLevelAt: number
  loadout: Loadout
  slots: readonly EquipmentSlotInfo[]
  items: ReadonlyMap<number, ItemInfo>
  onUnequip: (slot: number) => void
  /** Drop an inventory index onto a slot. The index arrives from the grid's drag. */
  onEquipIndex: (index: number) => void
  onClose: () => void
}

export function CharacterSheet({
  name,
  characterClass,
  level,
  experience,
  nextLevelAt,
  loadout,
  slots,
  items,
  onUnequip,
  onEquipIndex,
  onClose,
}: CharacterSheetProps) {
  const worn = new Map(loadout.equipped.map((entry) => [entry.slot, entry.itemId]))

  return (
    <section className="panel sheet" aria-label="Character">
      <div className="sheet-head">
        <span className="panel-title">Character</span>
        <button type="button" className="sheet-close" onClick={onClose} aria-label="Close">
          x
        </button>
      </div>

      <div className="sheet-identity">
        <strong>{name}</strong>
        <span className="muted">
          {characterClass.name} · level {level}
        </span>
        <span className="muted sheet-fantasy">{characterClass.fantasy}</span>
      </div>

      <dl className="sheet-stats">
        <dt>Health</dt>
        <dd>{loadout.maxHealth}</dd>
        <dt>Resource</dt>
        <dd>{loadout.maxResource}</dd>
        <dt>Damage bonus</dt>
        <dd>{loadout.bonusDamage > 0 ? `+${loadout.bonusDamage}` : '—'}</dd>
        <dt>Walk speed</dt>
        <dd>{loadout.moveSpeed.toFixed(2)}</dd>
        <dt>Experience</dt>
        <dd>
          {experience} / {nextLevelAt}
        </dd>
      </dl>

      <div className="sheet-slots">
        {slots.map((slot) => {
          const itemId = worn.get(slot.slot)
          const item = itemId === undefined ? undefined : items.get(itemId)
          return (
            <button
              type="button"
              key={slot.slot}
              className={`slot${item ? ` filled rarity-${item.rarity}` : ''}`}
              title={item ? `${item.name} — click to take off` : slot.name}
              onClick={() => {
                if (item !== undefined) onUnequip(slot.slot)
              }}
              // The grid is the drag source and this is the target, which is the
              // gesture people try first. Clicking a grid cell does the same thing.
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault()
                const index = Number(event.dataTransfer.getData('text/plain'))
                if (Number.isInteger(index)) onEquipIndex(index)
              }}
            >
              <span className="slot-name">{slot.name}</span>
              <span className="slot-item">{item?.name ?? '—'}</span>
            </button>
          )
        })}
      </div>
    </section>
  )
}
