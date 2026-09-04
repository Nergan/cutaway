/**
 * The pack: a fixed grid of stacks.
 *
 * Empty slots are drawn rather than omitted, because the bound is the point. A list
 * that grew as you picked things up would say nothing about how much room is left,
 * and the whole reason equipment is interesting is that carrying it costs something.
 *
 * Every action is a round trip. Nothing is applied optimistically: the server answers
 * each command with a whole new snapshot of the pack, so predicting the result would
 * only be a chance to briefly disagree with an answer already in flight.
 */

import { ITEM_CONSUMABLE, ITEM_EQUIPMENT, type ItemInfo } from './api'
import type { Loadout } from '../net/session'

export interface InventoryPanelProps {
  loadout: Loadout
  items: ReadonlyMap<number, ItemInfo>
  onEquip: (index: number) => void
  onUse: (index: number) => void
  onDrop: (index: number) => void
  onClose: () => void
}

export function InventoryPanel({
  loadout,
  items,
  onEquip,
  onUse,
  onDrop,
  onClose,
}: InventoryPanelProps) {
  const capacity = Math.max(loadout.capacity, loadout.stacks.length)
  const cells = Array.from({ length: capacity }, (_, index) => loadout.stacks[index])

  return (
    <section className="panel inventory" aria-label="Inventory">
      <div className="sheet-head">
        <span className="panel-title">
          Pack {loadout.stacks.length}/{capacity}
        </span>
        <button type="button" className="sheet-close" onClick={onClose} aria-label="Close">
          x
        </button>
      </div>

      <div className="inventory-grid">
        {cells.map((stack, index) => {
          const item = stack === undefined ? undefined : items.get(stack.itemId)
          if (stack === undefined || item === undefined) {
            return <span key={index} className="cell empty" aria-hidden="true" />
          }

          return (
            <button
              type="button"
              key={index}
              className={`cell filled rarity-${item.rarity}`}
              title={describe(item)}
              draggable
              onDragStart={(event) => event.dataTransfer.setData('text/plain', String(index))}
              onClick={() => {
                if (item.kind === ITEM_EQUIPMENT) onEquip(index)
                else if (item.kind === ITEM_CONSUMABLE) onUse(index)
              }}
              // Right-click discards. A modifier on the left button would collide with
              // the one the player is already holding to run.
              onContextMenu={(event) => {
                event.preventDefault()
                onDrop(index)
              }}
            >
              <span className="cell-name">{item.name}</span>
              {stack.count > 1 && <span className="cell-count">{stack.count}</span>}
            </button>
          )
        })}
      </div>

      <p className="muted inventory-hint">Click to equip or use · right-click to discard</p>
    </section>
  )
}

/** The tooltip: what it is, what it does, and what wearing it is worth. */
function describe(item: ItemInfo): string {
  const lines = [item.name, item.description]
  const effects: string[] = []

  if (item.bonusHealth) effects.push(`${signed(item.bonusHealth)} health`)
  if (item.bonusResource) effects.push(`${signed(item.bonusResource)} resource`)
  if (item.bonusDamage) effects.push(`${signed(item.bonusDamage)} damage`)
  if (item.bonusSpeed) effects.push(`${signed(item.bonusSpeed)} speed`)
  if (item.restoresHealth) effects.push(`restores ${item.restoresHealth} health`)
  if (item.restoresResource) effects.push(`restores ${item.restoresResource} resource`)

  if (effects.length > 0) lines.push(effects.join(', '))
  return lines.join('\n')
}

function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value)
}
