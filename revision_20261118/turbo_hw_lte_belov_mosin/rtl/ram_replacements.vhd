library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity lte_turbo_decoder_encoded_data_sram is
    generic (WIDTH : positive := 5);
    port (
        clka : in std_logic; wea : in std_logic_vector(0 downto 0);
        addra : in std_logic_vector(12 downto 0); dina : in std_logic_vector(WIDTH-1 downto 0);
        clkb : in std_logic; addrb : in std_logic_vector(12 downto 0);
        doutb : out std_logic_vector(WIDTH-1 downto 0)
    );
end entity;

architecture rtl of lte_turbo_decoder_encoded_data_sram is
    type ram_t is array (0 to 2050) of std_logic_vector(WIDTH-1 downto 0);
    signal ram : ram_t := (others => (others => '0'));
begin
    process (clka)
        variable a : natural;
    begin
        if rising_edge(clka) then
            a := to_integer(unsigned(addra));
            if wea(0) = '1' and a <= ram'high then ram(a) <= dina; end if;
        end if;
    end process;
    process (clkb)
        variable a : natural;
    begin
        if rising_edge(clkb) then
            a := to_integer(unsigned(addrb));
            if a <= ram'high then doutb <= ram(a); else doutb <= (others => '0'); end if;
        end if;
    end process;
end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
entity bcjr_turbo_decoder_alphas_sram is
    port (
        clka : in std_logic; wea : in std_logic_vector(0 downto 0);
        addra : in std_logic_vector(12 downto 0); dina : in std_logic_vector(55 downto 0);
        clkb : in std_logic; addrb : in std_logic_vector(12 downto 0);
        doutb : out std_logic_vector(55 downto 0)
    );
end entity;

architecture rtl of bcjr_turbo_decoder_alphas_sram is
    type ram_t is array (0 to 2050) of std_logic_vector(55 downto 0);
    signal ram : ram_t := (others => (others => '0'));
begin
    process (clka)
        variable a : natural;
    begin
        if rising_edge(clka) then
            a := to_integer(unsigned(addra));
            if wea(0) = '1' and a <= ram'high then ram(a) <= dina; end if;
        end if;
    end process;
    process (clkb)
        variable a : natural;
    begin
        if rising_edge(clkb) then
            a := to_integer(unsigned(addrb));
            if a <= ram'high then doutb <= ram(a); else doutb <= (others => '0'); end if;
        end if;
    end process;
end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
entity bcjr_turbo_decoder_llrs_sram is
    generic (WIDTH : positive := 5);
    port (
        clka : in std_logic; wea : in std_logic_vector(0 downto 0);
        addra : in std_logic_vector(12 downto 0); dina : in std_logic_vector(2*WIDTH-1 downto 0);
        douta : out std_logic_vector(2*WIDTH-1 downto 0);
        clkb : in std_logic; web : in std_logic_vector(0 downto 0);
        addrb : in std_logic_vector(12 downto 0); dinb : in std_logic_vector(2*WIDTH-1 downto 0);
        doutb : out std_logic_vector(2*WIDTH-1 downto 0)
    );
end entity;

architecture rtl of bcjr_turbo_decoder_llrs_sram is
    type ram_t is array (0 to 2050) of std_logic_vector(2*WIDTH-1 downto 0);
    signal ram : ram_t := (others => (others => '0'));
begin
    process (clka)
        variable a : natural;
    begin
        if rising_edge(clka) then
            a := to_integer(unsigned(addra));
            if a <= ram'high then
                if wea(0) = '1' then ram(a) <= dina; douta <= dina;
                else douta <= ram(a); end if;
            else douta <= (others => '0'); end if;
        end if;
    end process;
    process (clkb)
        variable a : natural;
    begin
        if rising_edge(clkb) then
            a := to_integer(unsigned(addrb));
            if a <= ram'high then
                -- This BCJR instance always ties WEB low.  Keep RAM writes
                -- in the port-A process only: two VHDL signal drivers on the
                -- same RAM resolved 1-versus-0 data to X in simulation.
                doutb <= ram(a);
            else doutb <= (others => '0'); end if;
        end if;
    end process;
end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
entity lte_interleaver_data_sram is
    generic (WIDTH : positive := 5);
    port (
        clka : in std_logic; wea : in std_logic_vector(0 downto 0);
        addra : in std_logic_vector(12 downto 0); dina : in std_logic_vector(WIDTH-1 downto 0);
        clkb : in std_logic; addrb : in std_logic_vector(12 downto 0);
        doutb : out std_logic_vector(WIDTH-1 downto 0)
    );
end entity;

architecture rtl of lte_interleaver_data_sram is
    type ram_t is array (0 to 2047) of std_logic_vector(WIDTH-1 downto 0);
    signal ram : ram_t := (others => (others => '0'));
begin
    process (clka)
        variable a : natural;
    begin
        if rising_edge(clka) then
            a := to_integer(unsigned(addra));
            if wea(0) = '1' and a <= ram'high then ram(a) <= dina; end if;
        end if;
    end process;
    process (clkb)
        variable a : natural;
    begin
        if rising_edge(clkb) then
            a := to_integer(unsigned(addrb));
            if a <= ram'high then doutb <= ram(a); else doutb <= (others => '0'); end if;
        end if;
    end process;
end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
entity lte_interleaver_table_sram is
    port (
        clka : in std_logic; wea : in std_logic_vector(0 downto 0);
        addra : in std_logic_vector(12 downto 0); dina : in std_logic_vector(12 downto 0);
        clkb : in std_logic; addrb : in std_logic_vector(12 downto 0);
        doutb : out std_logic_vector(12 downto 0)
    );
end entity;

architecture rtl of lte_interleaver_table_sram is
    type ram_t is array (0 to 2047) of std_logic_vector(12 downto 0);
    signal ram : ram_t := (others => (others => '0'));
begin
    process (clka)
        variable a : natural;
    begin
        if rising_edge(clka) then
            a := to_integer(unsigned(addra));
            if wea(0) = '1' and a <= ram'high then ram(a) <= dina; end if;
        end if;
    end process;
    process (clkb)
        variable a : natural;
    begin
        if rising_edge(clkb) then
            a := to_integer(unsigned(addrb));
            if a <= ram'high then doutb <= ram(a); else doutb <= (others => '0'); end if;
        end if;
    end process;
end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity turbo_derate_stream_sram is
    port (
        CLK     : in  std_logic;
        WE      : in  std_logic;
        ADDR    : in  std_logic_vector(11 downto 0);
        DIN     : in  std_logic_vector(4 downto 0);
        RD_ADDR : in  std_logic_vector(11 downto 0);
        DOUT    : out std_logic_vector(4 downto 0)
    );
end entity;

architecture rtl of turbo_derate_stream_sram is
    type ram_t is array (0 to 2051) of std_logic_vector(4 downto 0);
    signal ram : ram_t := (others => (others => '0'));
begin
    process (CLK)
        variable write_addr : natural;
        variable read_addr : natural;
    begin
        if rising_edge(CLK) then
            write_addr := to_integer(unsigned(ADDR));
            read_addr := to_integer(unsigned(RD_ADDR));
            if WE = '1' and write_addr <= ram'high then
                ram(write_addr) <= DIN;
            end if;
            if read_addr <= ram'high then
                DOUT <= ram(read_addr);
            else
                DOUT <= (others => '0');
            end if;
        end if;
    end process;
end architecture;

library ieee;
use ieee.std_logic_1164.all;
entity lte_interleaver_divider is
    port (
        rfd : out std_logic; clk : in std_logic;
        dividend : in std_logic_vector(25 downto 0);
        quotient : out std_logic_vector(25 downto 0);
        divisor : in std_logic_vector(12 downto 0);
        fractional : out std_logic_vector(12 downto 0)
    );
end entity;

architecture fixed_k2048 of lte_interleaver_divider is
    type rem_pipe_t is array (0 to 29) of std_logic_vector(12 downto 0);
    signal rem_pipe : rem_pipe_t := (others => (others => '0'));
begin
    rfd <= '1';
    quotient <= (others => '0');
    process (clk)
    begin
        if rising_edge(clk) then
            rem_pipe(0) <= "00" & dividend(10 downto 0);
            for i in 1 to 29 loop rem_pipe(i) <= rem_pipe(i-1); end loop;
        end if;
    end process;
    fractional <= rem_pipe(29);
end architecture;
