/**
 * Notification API — new file frontend/src/api/notify.ts (stage 4)
 * Contract: api-design v2.1 §10 (/notify), shapes @ backend schemas.
 * Channel config is write-only; reads return a masked config_mask. Test sends and
 * resend of failed records drive the outbound path.
 */
import http from './http'
import type {
  Page,
  ChannelCreate,
  ChannelUpdate,
  ChannelOut,
  ChannelStatusIn,
  ChannelTestIn,
  NotifyRecordOut,
  NotifyRecordQuery,
  Result,
} from './types'

export async function listChannels(): Promise<ChannelOut[]> {
  const { data } = await http.get<Result<ChannelOut[]>>('/notify/channels')
  return data.data
}

export async function createChannel(payload: ChannelCreate): Promise<ChannelOut> {
  const { data } = await http.post<Result<ChannelOut>>('/notify/channels', payload)
  return data.data
}

export async function updateChannel(channelId: number, payload: ChannelUpdate): Promise<void> {
  await http.put<Result<void>>(`/notify/channels/${channelId}`, payload)
}

export async function deleteChannel(channelId: number): Promise<void> {
  await http.delete<Result<void>>(`/notify/channels/${channelId}`)
}

export async function setChannelStatus(channelId: number, payload: ChannelStatusIn): Promise<void> {
  await http.put<Result<void>>(`/notify/channels/${channelId}/status`, payload)
}

export async function testChannel(channelId: number, payload: ChannelTestIn): Promise<NotifyRecordOut> {
  const { data } = await http.post<Result<NotifyRecordOut>>(`/notify/channels/${channelId}/test`, payload)
  return data.data
}

export async function listRecords(params?: NotifyRecordQuery): Promise<Page<NotifyRecordOut>> {
  const { data } = await http.get<Result<Page<NotifyRecordOut>>>('/notify/records', { params })
  return data.data
}

export async function resendRecord(recordId: number): Promise<NotifyRecordOut> {
  const { data } = await http.post<Result<NotifyRecordOut>>(`/notify/records/${recordId}/resend`)
  return data.data
}
