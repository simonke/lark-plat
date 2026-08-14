import type { Directive, DirectiveBinding } from 'vue'
import { useAuthStore } from '../stores/auth'

function removeElement(el: HTMLElement): void {
  el.parentNode?.removeChild(el)
}

export const vPerm: Directive<HTMLElement, string | string[]> = {
  mounted(el: HTMLElement, binding: DirectiveBinding<string | string[]>) {
    const auth = useAuthStore()
    const codes = Array.isArray(binding.value) ? binding.value : [binding.value]
    const allowed = auth.isAdmin || codes.some((c) => auth.hasPerm(c))
    if (!allowed) {
      removeElement(el)
    }
  },
}
