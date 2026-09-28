import type { CredentialCreate } from '../../api/types'

export interface CredentialSecretFields {
  type: 'password' | 'key'
  secret: string
  key: string
  passphrase: string
}

export function clearNonApplicableSecretFields(form: CredentialSecretFields): void {
  form.secret = ''
  form.key = ''
  form.passphrase = ''
}

export function buildCredentialCreatePayload(
  form: CredentialSecretFields & { host_id: number; username: string }
): CredentialCreate {
  const payload: CredentialCreate = { host_id: form.host_id, username: form.username, type: form.type }
  if (form.type === 'password') {
    payload.secret = form.secret
  } else {
    payload.key = form.key
    payload.passphrase = form.passphrase
  }
  return payload
}
