import { formatDuration } from './format'

test('durations read as seconds, minutes or hours', () => {
  expect(formatDuration(4.23)).toBe('4.2 s')
  expect(formatDuration(42)).toBe('42 s')
  expect(formatDuration(1800)).toBe('30 min')
  expect(formatDuration(725)).toBe('12 min 5 s')
  expect(formatDuration(4980)).toBe('1 h 23 min')
  expect(formatDuration(7200)).toBe('2 h')
})
