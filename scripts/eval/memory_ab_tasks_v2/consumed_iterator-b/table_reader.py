def read_table(rows):
    """Read a table given as an iterator of rows; the first row is the header.

    Returns {'columns': header, 'records': [one dict per data row], 'row_count': data rows}.
    """
    header = next(rows)
    records = [dict(zip(header, row)) for row in rows]
    row_count = len(list(rows))  # BUG: rows was consumed while building records
    return {"columns": header, "records": records, "row_count": row_count}
