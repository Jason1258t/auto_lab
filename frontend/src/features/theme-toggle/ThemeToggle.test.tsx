import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ThemeProvider } from '@/shared/lib/theme'

import { ThemeToggle } from './ThemeToggle'

test('the toggle goes system -> light -> dark and remembers the choice', async () => {
  render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  )
  const user = userEvent.setup()
  const button = screen.getByRole('button')
  expect(button).toHaveAccessibleName('Change theme (now: System theme)')

  await user.click(button)
  expect(document.documentElement).not.toHaveClass('dark')
  expect(localStorage.getItem('autolab.theme')).toBe('light')

  await user.click(button)
  expect(document.documentElement).toHaveClass('dark')
  expect(localStorage.getItem('autolab.theme')).toBe('dark')
})
