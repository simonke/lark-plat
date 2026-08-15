import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../src/stores/auth'
import { vPerm } from '../src/directives/perm'

function makeEl(): HTMLElement {
  return document.createElement('button')
}

function binding(value: string | string[]): { value: string | string[] } {
  return { value }
}

describe('v-perm directive', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('removes element when user lacks permission', () => {
    const store = useAuthStore()
    store.user = {
      id: 1,
      username: 'viewer',
      real_name: 'Viewer',
      roles: [],
      permissions: [],
      visible_group_ids: [],
      is_admin: false,
    }
    store.loaded = true
    const el = makeEl()
    const parent = document.createElement('div')
    parent.appendChild(el)
    vPerm.mounted(el, binding('system:user:del') as never)
    expect(parent.contains(el)).toBe(false)
  })

  it('keeps element when user has matching permission', () => {
    const store = useAuthStore()
    store.user = {
      id: 1,
      username: 'operator',
      real_name: 'Operator',
      roles: [],
      permissions: ['system:user:list'],
      visible_group_ids: [],
      is_admin: false,
    }
    store.loaded = true
    const el = makeEl()
    const parent = document.createElement('div')
    parent.appendChild(el)
    vPerm.mounted(el, binding('system:user:list') as never)
    expect(parent.contains(el)).toBe(true)
  })

  it('keeps element for any-of array when at least one matches', () => {
    const store = useAuthStore()
    store.user = {
      id: 1,
      username: 'operator',
      real_name: 'Operator',
      roles: [],
      permissions: ['system:role:list'],
      visible_group_ids: [],
      is_admin: false,
    }
    store.loaded = true
    const el = makeEl()
    const parent = document.createElement('div')
    parent.appendChild(el)
    vPerm.mounted(el, binding(['system:user:list', 'system:role:list']) as never)
    expect(parent.contains(el)).toBe(true)
  })

  it('removes element when none of the array matches', () => {
    const store = useAuthStore()
    store.user = {
      id: 1,
      username: 'viewer',
      real_name: 'Viewer',
      roles: [],
      permissions: [],
      visible_group_ids: [],
      is_admin: false,
    }
    store.loaded = true
    const el = makeEl()
    const parent = document.createElement('div')
    parent.appendChild(el)
    vPerm.mounted(el, binding(['system:user:list', 'system:role:list']) as never)
    expect(parent.contains(el)).toBe(false)
  })

  it('keeps element for admin regardless of permission', () => {
    const store = useAuthStore()
    store.user = {
      id: 1,
      username: 'admin',
      real_name: 'Admin',
      roles: [],
      permissions: [],
      visible_group_ids: [],
      is_admin: true,
    }
    store.loaded = true
    const el = makeEl()
    const parent = document.createElement('div')
    parent.appendChild(el)
    vPerm.mounted(el, binding('system:user:del') as never)
    expect(parent.contains(el)).toBe(true)
  })
})
