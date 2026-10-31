import {useDateFormat} from '../../i18n/dates';

/** One way to show a date in the console: a <time> element in the reader's language, with
 *  the moment in UTC on hover, so two people in different timezones can say which one
 *  they mean.
 *
 *  `moment` shows the time of day as well, in the reader's own timezone (a last action, a
 *  last engagement); without it the calendar day is shown (the day someone was invited or
 *  blocked), which does not move with the reader's timezone. Both come from the site's
 *  date helpers (`i18n/dates.ts`). */
export function AdminTime({value, moment = false}: {value: string; moment?: boolean}) {
  const {date, dateTime} = useDateFormat();
  const parsed = new Date(value);
  const utc = Number.isNaN(parsed.getTime())
    ? value : `${parsed.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
  return (
    <time className="admin-time" dateTime={value} title={utc}>
      {moment ? dateTime(value) : date(value)}
    </time>
  );
}
